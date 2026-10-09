from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select

from repoman.api.v1.jobs import JobOut
from repoman.auth.dependencies import AdminPrincipal
from repoman.db.deps import DbSession
from repoman.db.models import Blob, BlobStore
from repoman.errors import ApiError
from repoman.jobs.queue import enqueue
from repoman.storage.policy import BLOB_MIGRATE_JOB
from repoman.storage.service import BlobService, is_low_space, low_space_threshold
from repoman.storage.stores import (
    STORE_NAME_PATTERN,
    active_migration,
    check_path,
    has_blobs,
    is_default,
    validate_new_path,
)

router = APIRouter(prefix="/blob-stores", tags=["storage"])

StoreName = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
    StringConstraints(pattern=STORE_NAME_PATTERN),
]
StorePath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)]
Quota = Annotated[int, Field(ge=1)]


class BlobStoreOut(BaseModel):
    id: int
    name: str
    type: str
    is_default: bool
    path: str | None
    available: bool
    total_bytes: int | None
    free_bytes: int | None
    low_space_threshold_bytes: int | None
    low_space: bool
    quota_bytes: int | None
    quota_exceeded: bool
    blob_count: int
    used_bytes: int
    pending_delete_count: int
    pending_delete_bytes: int
    migration_job_id: int | None
    created_at: datetime


class BlobStoreCreateIn(BaseModel):
    name: StoreName
    type: Literal["filesystem"] = "filesystem"
    path: StorePath
    quota_bytes: Quota | None = None


class BlobStoreUpdateIn(BaseModel):
    """Omitted fields are left unchanged; quota_bytes = null removes the quota."""

    model_config = ConfigDict(extra="forbid")

    name: StoreName | None = None
    path: StorePath | None = None
    quota_bytes: Quota | None = None


class BlobStoreCheckOut(BaseModel):
    ok: bool
    error_code: str | None = None
    message: str | None = None
    total_bytes: int | None = None
    free_bytes: int | None = None


class MigrateIn(BaseModel):
    target_store_id: int


def _service(request: Request) -> BlobService:
    return request.app.state.blobs


async def _get_store(db: DbSession, store_id: int) -> BlobStore:
    store = await db.get(BlobStore, store_id)
    if store is None:
        raise ApiError(404, "blob_store_not_found", "Blob store not found")
    return store


async def _store_out(db: DbSession, service: BlobService, store: BlobStore) -> BlobStoreOut:
    usage = await (await service.storage(db, store.id)).usage()
    rows = (
        await db.execute(
            select(
                Blob.deleted_at.is_(None),
                func.count(Blob.id),
                func.coalesce(func.sum(Blob.size), 0),
            )
            .where(Blob.blob_store_id == store.id)
            .group_by(Blob.deleted_at.is_(None))
        )
    ).all()
    counts = {live: (int(count), int(size)) for live, count, size in rows}
    live_count, live_bytes = counts.get(True, (0, 0))
    pending_count, pending_bytes = counts.get(False, (0, 0))
    migration = await active_migration(db, store.id)
    return BlobStoreOut(
        id=store.id,
        name=store.name,
        type=store.type,
        is_default=is_default(store),
        path=store.config.get("path"),
        available=usage is not None and Path(store.config.get("path", "")).is_dir(),
        total_bytes=usage.total_bytes if usage else None,
        free_bytes=usage.free_bytes if usage else None,
        low_space_threshold_bytes=low_space_threshold(usage) if usage else None,
        low_space=is_low_space(usage),
        quota_bytes=store.quota_bytes,
        quota_exceeded=(
            store.quota_bytes is not None and live_bytes + pending_bytes >= store.quota_bytes
        ),
        blob_count=live_count,
        used_bytes=live_bytes,
        pending_delete_count=pending_count,
        pending_delete_bytes=pending_bytes,
        migration_job_id=migration.id if migration else None,
        created_at=store.created_at,
    )


@router.get("", response_model=list[BlobStoreOut])
async def list_blob_stores(
    request: Request, _: AdminPrincipal, db: DbSession
) -> list[BlobStoreOut]:
    stores = await db.scalars(select(BlobStore).order_by(BlobStore.id))
    return [await _store_out(db, _service(request), store) for store in stores]


@router.post("", response_model=BlobStoreOut, status_code=201)
async def create_blob_store(
    body: BlobStoreCreateIn, request: Request, _: AdminPrincipal, db: DbSession
) -> BlobStoreOut:
    if await db.scalar(select(BlobStore.id).where(BlobStore.name == body.name)):
        raise ApiError(409, "blob_store_name_taken", "Blob store name is already taken")
    path = await validate_new_path(db, body.path)
    store = BlobStore(
        name=body.name, type=body.type, config={"path": str(path)}, quota_bytes=body.quota_bytes
    )
    db.add(store)
    await db.commit()
    return await _store_out(db, _service(request), store)


@router.get("/{store_id}", response_model=BlobStoreOut)
async def get_blob_store(
    store_id: int, request: Request, _: AdminPrincipal, db: DbSession
) -> BlobStoreOut:
    return await _store_out(db, _service(request), await _get_store(db, store_id))


@router.patch("/{store_id}", response_model=BlobStoreOut)
async def update_blob_store(
    store_id: int, body: BlobStoreUpdateIn, request: Request, _: AdminPrincipal, db: DbSession
) -> BlobStoreOut:
    store = await _get_store(db, store_id)
    fields = body.model_fields_set
    if "name" in fields and body.name and body.name != store.name:
        if is_default(store):
            raise ApiError(409, "blob_store_is_default", "The default blob store cannot be renamed")
        if await db.scalar(select(BlobStore.id).where(BlobStore.name == body.name)):
            raise ApiError(409, "blob_store_name_taken", "Blob store name is already taken")
        store.name = body.name
    if "path" in fields and body.path:
        if is_default(store):
            raise ApiError(
                409,
                "blob_store_is_default",
                "The path of the default blob store is set by REPOMAN_STORAGE_PATH",
            )
        new_path = Path(body.path).resolve() if Path(body.path).is_absolute() else None
        if new_path is None or str(new_path) != store.config.get("path"):
            if await has_blobs(db, store.id) or await active_migration(db, store.id):
                raise ApiError(
                    409,
                    "blob_store_not_empty",
                    "The path can be changed only for an empty blob store",
                )
            path = await validate_new_path(db, body.path, exclude_store_id=store.id)
            store.config = {**store.config, "path": str(path)}
    if "quota_bytes" in fields:
        store.quota_bytes = body.quota_bytes
    await db.commit()
    _service(request).forget(store.id)
    return await _store_out(db, _service(request), store)


@router.delete("/{store_id}", status_code=204)
async def delete_blob_store(
    store_id: int, request: Request, _: AdminPrincipal, db: DbSession
) -> Response:
    store = await _get_store(db, store_id)
    if is_default(store):
        raise ApiError(409, "blob_store_is_default", "The default blob store cannot be deleted")
    if await active_migration(db, store.id):
        raise ApiError(409, "blob_store_in_use", "A migration of this blob store is in progress")
    if await has_blobs(db, store.id):
        raise ApiError(409, "blob_store_not_empty", "Only an empty blob store can be deleted")
    # Repositories referencing the store are checked here once repositories exist.
    await db.delete(store)
    await db.commit()
    _service(request).forget(store_id)
    return Response(status_code=204)


@router.post("/{store_id}/check", response_model=BlobStoreCheckOut)
async def check_blob_store(
    store_id: int, request: Request, _: AdminPrincipal, db: DbSession
) -> BlobStoreCheckOut:
    store = await _get_store(db, store_id)
    result = await check_path(Path(store.config.get("path", "")))
    usage = await (await _service(request).storage(db, store.id)).usage()
    return BlobStoreCheckOut(
        ok=result.ok,
        error_code=result.error_code,
        message=result.message,
        total_bytes=usage.total_bytes if usage else None,
        free_bytes=usage.free_bytes if usage else None,
    )


@router.post("/{store_id}/migrate", response_model=JobOut, status_code=202)
async def migrate_blob_store(
    store_id: int, body: MigrateIn, request: Request, principal: AdminPrincipal, db: DbSession
) -> JobOut:
    """Move all blobs of the store to another store (background job)."""
    source = await _get_store(db, store_id)
    target = await _get_store(db, body.target_store_id)
    if source.id == target.id:
        raise ApiError(422, "blob_store_same", "Source and target blob stores are the same")
    job = await enqueue(
        db,
        BLOB_MIGRATE_JOB,
        params={"source_store_id": source.id, "target_store_id": target.id},
        # One migration at a time: it is I/O heavy.
        resource_key=BLOB_MIGRATE_JOB,
        created_by_id=principal.user.id if principal.user else None,
    )
    await db.commit()
    request.app.state.job_runner.wake()
    return JobOut.of(job)
