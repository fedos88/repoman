"""Storage backend interface (design §7.2).

Backends store immutable objects under blob ids and know nothing about repositories;
which blobs exist is recorded in the database (table `blobs`).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID


class BlobNotFoundError(Exception):
    pass


class StorageFullError(Exception):
    """No space left, or free space is below the low-space threshold."""


@dataclass(frozen=True)
class BlobStat:
    blob_id: UUID
    size: int
    modified_at: datetime


@dataclass(frozen=True)
class StorageUsage:
    total_bytes: int
    free_bytes: int


class BlobWriter(Protocol):
    async def write(self, data: bytes) -> None: ...

    async def commit(self) -> None:
        """Make the object durable and visible under its blob id."""

    async def abort(self) -> None:
        """Discard a not yet committed object."""


class BlobStorage(Protocol):
    async def open_write(self, blob_id: UUID) -> BlobWriter: ...

    async def open_read(
        self, blob_id: UUID, start: int = 0, end: int | None = None
    ) -> AsyncIterator[bytes]:
        """Bytes [start, end) of the object; raises BlobNotFoundError."""

    async def stat(self, blob_id: UUID) -> BlobStat | None: ...

    async def delete(self, blob_id: UUID) -> None:
        """Delete the object; a missing object is not an error."""

    def iterate(self) -> AsyncIterator[BlobStat]:
        """All committed objects (used to find orphans)."""

    async def usage(self) -> StorageUsage | None: ...

    async def cleanup_temp(self, older_than: timedelta) -> int:
        """Remove abandoned temporary files; returns the number removed."""
