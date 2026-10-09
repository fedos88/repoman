"""Blob store management rules: path validation, availability check, usage."""

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.db.models import JOB_ACTIVE_STATUSES, Blob, BlobStore, Job
from repoman.errors import ApiError
from repoman.storage.policy import BLOB_MIGRATE_JOB, DEFAULT_STORE_NAME

STORE_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"


@dataclass
class CheckResult:
    ok: bool
    error_code: str | None = None
    message: str | None = None


def _probe_writable(path: Path, create: bool) -> None:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    probe = path / f".repoman-probe-{uuid.uuid4().hex}"
    probe.write_bytes(b"ok")
    probe.unlink()


async def check_path(path: Path, *, create: bool = False) -> CheckResult:
    """The directory is writable; it is created only when `create` is set.

    An existing store is checked without creating the directory: a missing mount point
    must be reported, not silently replaced by a directory on another filesystem.
    """
    if not create and not await asyncio.to_thread(path.is_dir):
        return CheckResult(False, "blob_store_path_missing", f"{path}: directory does not exist")
    try:
        await asyncio.to_thread(_probe_writable, path, create)
    except OSError as exc:
        return CheckResult(False, "blob_store_path_not_writable", f"{path}: {exc.strerror or exc}")
    return CheckResult(True)


async def validate_new_path(
    db: AsyncSession, raw: str, exclude_store_id: int | None = None
) -> Path:
    """Absolute, not overlapping with other stores, writable. Returns the normalized path."""
    path = Path(raw.strip())
    if not path.is_absolute():
        raise ApiError(422, "blob_store_path_invalid", "The path must be absolute")
    path = path.resolve()
    query = select(BlobStore).where(BlobStore.type == "filesystem")
    if exclude_store_id is not None:
        query = query.where(BlobStore.id != exclude_store_id)
    for other in await db.scalars(query):
        other_path = Path(other.config.get("path", "")).resolve()
        if path == other_path or path.is_relative_to(other_path) or other_path.is_relative_to(path):
            raise ApiError(
                409,
                "blob_store_path_overlap",
                f"The path overlaps with blob store {other.name}",
                {"store": other.name},
            )
    result = await check_path(path, create=True)
    if not result.ok:
        raise ApiError(
            422, result.error_code or "blob_store_path_not_writable", result.message or ""
        )
    return path


async def has_blobs(db: AsyncSession, store_id: int) -> bool:
    """Any blob rows, including those pending deletion (still on disk)."""
    return (
        await db.scalar(select(Blob.id).where(Blob.blob_store_id == store_id).limit(1))
    ) is not None


async def active_migration(db: AsyncSession, store_id: int) -> Job | None:
    return await db.scalar(
        select(Job)
        .where(
            Job.type == BLOB_MIGRATE_JOB,
            Job.status.in_(JOB_ACTIVE_STATUSES),
            or_(
                Job.params["source_store_id"].as_integer() == store_id,
                Job.params["target_store_id"].as_integer() == store_id,
            ),
        )
        .limit(1)
    )


def is_default(store: BlobStore) -> bool:
    return store.name == DEFAULT_STORE_NAME
