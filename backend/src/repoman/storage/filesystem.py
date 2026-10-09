"""Filesystem storage backend (design §7.3).

Layout: {root}/blobs/{id[0:2]}/{id[2:4]}/{id}; temporary files in {root}/.tmp on the
same filesystem, so committing is an atomic rename.
"""

import asyncio
import errno
import os
import shutil
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from repoman.storage.base import BlobNotFoundError, BlobStat, StorageFullError, StorageUsage

READ_CHUNK_SIZE = 1024 * 1024


def _raise_if_full(exc: OSError) -> None:
    if exc.errno in (errno.ENOSPC, errno.EDQUOT):
        raise StorageFullError(str(exc)) from exc


class FilesystemBlobWriter:
    def __init__(self, temp_path: Path, final_path: Path, file: BinaryIO) -> None:
        self.temp_path = temp_path
        self.final_path = final_path
        self._file: BinaryIO | None = file

    async def write(self, data: bytes) -> None:
        assert self._file is not None, "writer is closed"
        try:
            await asyncio.to_thread(self._file.write, data)
        except OSError as exc:
            _raise_if_full(exc)
            raise

    def _commit(self) -> None:
        assert self._file is not None, "writer is closed"
        file, self._file = self._file, None
        try:
            file.flush()
            os.fsync(file.fileno())
        finally:
            file.close()
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.temp_path, self.final_path)

    async def commit(self) -> None:
        try:
            await asyncio.to_thread(self._commit)
        except OSError as exc:
            await self.abort()
            _raise_if_full(exc)
            raise

    def _abort(self) -> None:
        if self._file is not None:
            file, self._file = self._file, None
            file.close()
        self.temp_path.unlink(missing_ok=True)

    async def abort(self) -> None:
        await asyncio.to_thread(self._abort)


class FilesystemBlobStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.blobs_dir = root / "blobs"
        self.temp_dir = root / ".tmp"

    def path_for(self, blob_id: UUID) -> Path:
        name = str(blob_id)
        return self.blobs_dir / blob_id.hex[0:2] / blob_id.hex[2:4] / name

    async def open_write(self, blob_id: UUID) -> FilesystemBlobWriter:
        temp_path = self.temp_dir / f"{blob_id}.part"

        def _open() -> BinaryIO:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            return temp_path.open("xb")

        try:
            file = await asyncio.to_thread(_open)
        except OSError as exc:
            _raise_if_full(exc)
            raise
        return FilesystemBlobWriter(temp_path, self.path_for(blob_id), file)

    async def open_read(
        self, blob_id: UUID, start: int = 0, end: int | None = None
    ) -> AsyncIterator[bytes]:
        path = self.path_for(blob_id)
        try:
            file = await asyncio.to_thread(path.open, "rb")
        except FileNotFoundError:
            raise BlobNotFoundError(str(blob_id)) from None
        return self._read(file, start, end)

    @staticmethod
    async def _read(file: BinaryIO, start: int, end: int | None) -> AsyncIterator[bytes]:
        try:
            if start:
                await asyncio.to_thread(file.seek, start)
            remaining = None if end is None else max(end - start, 0)
            while remaining is None or remaining > 0:
                size = READ_CHUNK_SIZE if remaining is None else min(READ_CHUNK_SIZE, remaining)
                chunk = await asyncio.to_thread(file.read, size)
                if not chunk:
                    break
                if remaining is not None:
                    remaining -= len(chunk)
                yield chunk
        finally:
            await asyncio.to_thread(file.close)

    async def stat(self, blob_id: UUID) -> BlobStat | None:
        try:
            result = await asyncio.to_thread(self.path_for(blob_id).stat)
        except FileNotFoundError:
            return None
        return BlobStat(blob_id, result.st_size, datetime.fromtimestamp(result.st_mtime, UTC))

    async def delete(self, blob_id: UUID) -> None:
        await asyncio.to_thread(self.path_for(blob_id).unlink, True)

    @staticmethod
    def _scan(directory: Path) -> list[BlobStat]:
        result = []
        try:
            entries = list(os.scandir(directory))
        except FileNotFoundError:
            return result
        for entry in entries:
            try:
                blob_id = UUID(entry.name)
                info = entry.stat()
            except (ValueError, FileNotFoundError):
                continue  # not a blob, or removed concurrently
            result.append(
                BlobStat(blob_id, info.st_size, datetime.fromtimestamp(info.st_mtime, UTC))
            )
        return result

    async def iterate(self) -> AsyncIterator[BlobStat]:
        def _subdirs(directory: Path) -> list[Path]:
            try:
                return sorted(p for p in directory.iterdir() if p.is_dir())
            except FileNotFoundError:
                return []

        for level1 in await asyncio.to_thread(_subdirs, self.blobs_dir):
            for level2 in await asyncio.to_thread(_subdirs, level1):
                for item in await asyncio.to_thread(self._scan, level2):
                    yield item

    async def usage(self) -> StorageUsage | None:
        try:
            result = await asyncio.to_thread(shutil.disk_usage, self.root)
        except FileNotFoundError:
            return None
        return StorageUsage(total_bytes=result.total, free_bytes=result.free)

    async def cleanup_temp(self, older_than: timedelta) -> int:
        threshold = time.time() - older_than.total_seconds()

        def _cleanup() -> int:
            removed = 0
            try:
                entries = list(os.scandir(self.temp_dir))
            except FileNotFoundError:
                return 0
            for entry in entries:
                try:
                    if entry.is_file() and entry.stat().st_mtime < threshold:
                        os.unlink(entry.path)
                        removed += 1
                except FileNotFoundError:
                    continue
            return removed

        return await asyncio.to_thread(_cleanup)
