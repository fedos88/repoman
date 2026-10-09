"""Blobs on top of storage backends: the database records which blobs exist."""

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.db.models import Blob, BlobStore
from repoman.storage.base import BlobStorage, BlobWriter, StorageFullError, StorageUsage
from repoman.storage.filesystem import FilesystemBlobStorage
from repoman.storage.policy import DEFAULT_STORE_NAME, LOW_SPACE_MIN_BYTES, LOW_SPACE_RATIO


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

    async def commit(self, db: AsyncSession) -> Blob:
        """Finalize the object and add its row to the session (committed by the caller).

        If the caller's transaction fails, the object becomes an orphan and is removed
        by the cleanup job.
        """
        await self._writer.commit()
        self._done = True
        blob = Blob(
            id=self.blob_id,
            blob_store_id=self.store_id,
            size=self.size,
            sha256=self._sha256.hexdigest(),
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
        """Drop the cached backend after the store configuration changed."""
        self._storages.pop(store_id, None)

    @staticmethod
    async def default_store_id(db: AsyncSession) -> int:
        store_id = await db.scalar(select(BlobStore.id).where(BlobStore.name == DEFAULT_STORE_NAME))
        if store_id is None:
            raise LookupError("Default blob store is not initialized")
        return store_id

    async def upload(self, db: AsyncSession, store_id: int) -> BlobUpload:
        """Start writing a new blob; raises StorageFullError when space is low."""
        storage = await self.storage(db, store_id)
        if is_low_space(await storage.usage()):
            raise StorageFullError("Free space is below the low-space threshold")
        blob_id = uuid.uuid4()
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
