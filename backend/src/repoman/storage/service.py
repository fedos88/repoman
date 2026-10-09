"""Blobs on top of storage backends: the database records which blobs exist."""

import hashlib
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.db.models import Blob, BlobStore
from repoman.storage.base import (
    BlobStorage,
    BlobWriter,
    QuotaExceededError,
    StorageFullError,
    StorageUsage,
)
from repoman.storage.filesystem import FilesystemBlobStorage
from repoman.storage.policy import (
    DEFAULT_STORE_NAME,
    LOW_SPACE_MIN_BYTES,
    LOW_SPACE_RATIO,
    STORED_BYTES_CACHE_SECONDS,
)


def low_space_threshold(usage: StorageUsage) -> int:
    return max(int(usage.total_bytes * LOW_SPACE_RATIO), LOW_SPACE_MIN_BYTES)


def is_low_space(usage: StorageUsage | None) -> bool:
    return usage is not None and usage.free_bytes < low_space_threshold(usage)


class BlobUpload:
    """A blob being written. Use as `async with`; not committed blobs are discarded."""

    def __init__(self, store_id: int, blob_id: uuid.UUID, writer: BlobWriter) -> None:
        self.store_id = store_id
        self.blob_id = blob_id
        self.size = 0
        self._writer = writer
        self._sha256 = hashlib.sha256()
        self._done = False

    async def write(self, data: bytes) -> None:
        self._sha256.update(data)
        self.size += len(data)
        await self._writer.write(data)

    @property
    def sha256(self) -> str:
        return self._sha256.hexdigest()

    async def finish(self) -> None:
        """Finalize the object in the storage without touching the database."""
        await self._writer.commit()
        self._done = True

    async def commit(self, db: AsyncSession) -> Blob:
        """Finalize the object and add its row to the session (committed by the caller).

        If the caller's transaction fails, the object becomes an orphan and is removed
        by the cleanup job.
        """
        await self.finish()
        blob = Blob(
            id=self.blob_id,
            blob_store_id=self.store_id,
            size=self.size,
            sha256=self.sha256,
            created_at=datetime.now(UTC),
        )
        db.add(blob)
        return blob

    async def abort(self) -> None:
        if not self._done:
            self._done = True
            await self._writer.abort()

    async def __aenter__(self) -> "BlobUpload":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.abort()


class BlobService:
    def __init__(self) -> None:
        self._storages: dict[int, BlobStorage] = {}
        # store id -> (stored bytes, monotonic time of the query), for quota checks
        self._stored_bytes: dict[int, tuple[int, float]] = {}

    @staticmethod
    def storage_for(store: BlobStore) -> BlobStorage:
        if store.type == "filesystem":
            return FilesystemBlobStorage(Path(store.config["path"]))
        raise ValueError(f"Unsupported blob store type: {store.type}")

    async def storage(self, db: AsyncSession, store_id: int) -> BlobStorage:
        storage = self._storages.get(store_id)
        if storage is None:
            store = await db.get(BlobStore, store_id)
            if store is None:
                raise LookupError(f"Blob store {store_id} not found")
            storage = self._storages[store_id] = self.storage_for(store)
        return storage

    def forget(self, store_id: int) -> None:
        """Drop cached state after the store configuration changed."""
        self._storages.pop(store_id, None)
        self._stored_bytes.pop(store_id, None)

    @staticmethod
    async def default_store_id(db: AsyncSession) -> int:
        store_id = await db.scalar(select(BlobStore.id).where(BlobStore.name == DEFAULT_STORE_NAME))
        if store_id is None:
            raise LookupError("Default blob store is not initialized")
        return store_id

    @staticmethod
    async def stored_bytes(db: AsyncSession, store_id: int) -> int:
        """Size of all blobs of a store, including those pending deletion (still on disk)."""
        value = await db.scalar(
            select(func.coalesce(func.sum(Blob.size), 0)).where(Blob.blob_store_id == store_id)
        )
        return int(value or 0)

    async def _cached_stored_bytes(self, db: AsyncSession, store_id: int) -> int:
        cached = self._stored_bytes.get(store_id)
        now = time.monotonic()
        if cached is None or now - cached[1] > STORED_BYTES_CACHE_SECONDS:
            cached = (await self.stored_bytes(db, store_id), now)
            self._stored_bytes[store_id] = cached
        return cached[0]

    async def check_capacity(self, db: AsyncSession, store_id: int) -> None:
        """Raise StorageFullError if the store must not receive new blobs."""
        store = await db.get(BlobStore, store_id)
        if store is None:
            raise LookupError(f"Blob store {store_id} not found")
        if store.quota_bytes is not None:
            if await self._cached_stored_bytes(db, store_id) >= store.quota_bytes:
                raise QuotaExceededError(f"Quota of blob store {store.name} is exceeded")
        if is_low_space(await (await self.storage(db, store_id)).usage()):
            raise StorageFullError("Free space is below the low-space threshold")

    async def upload(
        self, db: AsyncSession, store_id: int, blob_id: uuid.UUID | None = None
    ) -> BlobUpload:
        """Start writing a blob (a new id unless given); raises StorageFullError."""
        await self.check_capacity(db, store_id)
        storage = await self.storage(db, store_id)
        blob_id = blob_id or uuid.uuid4()
        return BlobUpload(store_id, blob_id, await storage.open_write(blob_id))

    async def read(
        self, db: AsyncSession, blob: Blob, start: int = 0, end: int | None = None
    ) -> AsyncIterator[bytes]:
        storage = await self.storage(db, blob.blob_store_id)
        return await storage.open_read(blob.id, start, end)

    @staticmethod
    def mark_deleted(blob: Blob) -> None:
        """Schedule physical removal after the grace period (in the caller's transaction)."""
        if blob.deleted_at is None:
            blob.deleted_at = datetime.now(UTC)
