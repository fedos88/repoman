from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from repoman.auth.dependencies import AdminPrincipal
from repoman.db.deps import DbSession
from repoman.db.models import Blob, BlobStore
from repoman.errors import ApiError
from repoman.storage.service import BlobService, is_low_space, low_space_threshold

router = APIRouter(prefix="/blob-stores", tags=["storage"])


class BlobStoreOut(BaseModel):
    id: int
    name: str
    type: str
    path: str | None
    total_bytes: int | None
    free_bytes: int | None
    low_space_threshold_bytes: int | None
    low_space: bool
    blob_count: int
    used_bytes: int
    pending_delete_count: int
    pending_delete_bytes: int
    created_at: datetime


async def _store_out(db: DbSession, service: BlobService, store: BlobStore) -> BlobStoreOut:
    usage = await (await service.storage(db, store.id)).usage()
    live = (
        await db.execute(
            select(func.count(Blob.id), func.coalesce(func.sum(Blob.size), 0)).where(
                Blob.blob_store_id == store.id, Blob.deleted_at.is_(None)
            )
        )
    ).one()
    pending = (
        await db.execute(
            select(func.count(Blob.id), func.coalesce(func.sum(Blob.size), 0)).where(
                Blob.blob_store_id == store.id, Blob.deleted_at.is_not(None)
            )
        )
    ).one()
    return BlobStoreOut(
        id=store.id,
        name=store.name,
        type=store.type,
        path=store.config.get("path"),
        total_bytes=usage.total_bytes if usage else None,
        free_bytes=usage.free_bytes if usage else None,
        low_space_threshold_bytes=low_space_threshold(usage) if usage else None,
        low_space=is_low_space(usage),
        blob_count=live[0],
        used_bytes=int(live[1]),
        pending_delete_count=pending[0],
        pending_delete_bytes=int(pending[1]),
        created_at=store.created_at,
    )


@router.get("", response_model=list[BlobStoreOut])
async def list_blob_stores(
    request: Request, _: AdminPrincipal, db: DbSession
) -> list[BlobStoreOut]:
    service: BlobService = request.app.state.blobs
    stores = await db.scalars(select(BlobStore).order_by(BlobStore.id))
    return [await _store_out(db, service, store) for store in stores]


@router.get("/{store_id}", response_model=BlobStoreOut)
async def get_blob_store(
    store_id: int, request: Request, _: AdminPrincipal, db: DbSession
) -> BlobStoreOut:
    store = await db.get(BlobStore, store_id)
    if store is None:
        raise ApiError(404, "blob_store_not_found", "Blob store not found")
    return await _store_out(db, request.app.state.blobs, store)
