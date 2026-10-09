import hashlib
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from repoman.db.models import Blob, BlobStore, Job, Schedule
from repoman.jobs.queue import enqueue
from repoman.storage.base import BlobNotFoundError, StorageFullError, StorageUsage
from repoman.storage.bootstrap import ensure_default_store
from repoman.storage.filesystem import FilesystemBlobStorage
from repoman.storage.policy import BLOB_GC_JOB, STORE_CLEANUP_JOB
from repoman.storage.service import BlobService, is_low_space

GiB = 1024**3


async def read_all(iterator) -> bytes:
    return b"".join([chunk async for chunk in iterator])


def make_old(path: Path, age: timedelta = timedelta(days=2)) -> None:
    stamp = time.time() - age.total_seconds()
    os.utime(path, (stamp, stamp))


# --- filesystem backend (no database) ---------------------------------------------------


async def test_filesystem_write_read_range(tmp_path: Path) -> None:
    storage = FilesystemBlobStorage(tmp_path)
    blob_id = uuid.uuid4()
    writer = await storage.open_write(blob_id)
    await writer.write(b"hello ")
    await writer.write(b"world")
    assert await storage.stat(blob_id) is None  # not visible before commit
    await writer.commit()

    path = storage.path_for(blob_id)
    assert path.parent.parent.name == blob_id.hex[:2] and path.parent.name == blob_id.hex[2:4]
    assert await read_all(await storage.open_read(blob_id)) == b"hello world"
    assert await read_all(await storage.open_read(blob_id, 6)) == b"world"
    assert await read_all(await storage.open_read(blob_id, 0, 5)) == b"hello"
    assert (await storage.stat(blob_id)).size == 11
    assert [item.blob_id async for item in storage.iterate()] == [blob_id]
    assert list((tmp_path / ".tmp").iterdir()) == []

    await storage.delete(blob_id)
    await storage.delete(blob_id)  # missing is not an error
    with pytest.raises(BlobNotFoundError):
        await storage.open_read(blob_id)


async def test_filesystem_abort_and_temp_cleanup(tmp_path: Path) -> None:
    storage = FilesystemBlobStorage(tmp_path)
    writer = await storage.open_write(uuid.uuid4())
    await writer.write(b"partial")
    await writer.abort()
    assert list((tmp_path / ".tmp").iterdir()) == []
    assert [item async for item in storage.iterate()] == []

    old = tmp_path / ".tmp" / "old.part"
    new = tmp_path / ".tmp" / "new.part"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    make_old(old)
    assert await storage.cleanup_temp(timedelta(hours=24)) == 1
    assert [p.name for p in (tmp_path / ".tmp").iterdir()] == ["new.part"]


def test_low_space_threshold() -> None:
    assert not is_low_space(StorageUsage(total_bytes=1000 * GiB, free_bytes=60 * GiB))
    assert is_low_space(StorageUsage(total_bytes=1000 * GiB, free_bytes=40 * GiB))  # < 5%
    assert is_low_space(StorageUsage(total_bytes=100 * GiB, free_bytes=9 * GiB))  # < 10 GiB
    assert not is_low_space(None)


# --- blobs with the database ------------------------------------------------------------


@pytest.fixture
async def store_id(app: FastAPI) -> int:
    return await ensure_default_store(app.state.db_sessionmaker, app.state.settings)


@pytest.fixture
def blobs(app: FastAPI) -> BlobService:
    return app.state.blobs


async def create_blob(app: FastAPI, blobs: BlobService, store_id: int, data: bytes) -> Blob:
    async with app.state.db_sessionmaker() as db:
        async with await blobs.upload(db, store_id) as upload:
            await upload.write(data)
            blob = await upload.commit(db)
        await db.commit()
        return blob


async def test_default_store_is_idempotent(app: FastAPI, store_id: int) -> None:
    assert await ensure_default_store(app.state.db_sessionmaker, app.state.settings) == store_id
    async with app.state.db_sessionmaker() as db:
        stores = list(await db.scalars(select(BlobStore)))
        schedules = set(await db.scalars(select(Schedule.job_type)))
    assert [(s.name, s.type, s.config["path"]) for s in stores] == [
        ("default", "filesystem", str(app.state.settings.storage_path.resolve()))
    ]
    assert schedules == {BLOB_GC_JOB, STORE_CLEANUP_JOB}


async def test_upload_records_size_and_sha256(app: FastAPI, blobs, store_id) -> None:
    data = b"package contents" * 1000
    blob = await create_blob(app, blobs, store_id, data)
    assert blob.size == len(data)
    assert blob.sha256 == hashlib.sha256(data).hexdigest()
    async with app.state.db_sessionmaker() as db:
        saved = await db.get(Blob, blob.id)
        assert await read_all(await blobs.read(db, saved)) == data
        assert await read_all(await blobs.read(db, saved, 7, 15)) == data[7:15]


async def test_failed_upload_leaves_nothing(app: FastAPI, blobs, store_id) -> None:
    storage = FilesystemBlobStorage(app.state.settings.storage_path)
    async with app.state.db_sessionmaker() as db:
        with pytest.raises(RuntimeError):
            async with await blobs.upload(db, store_id) as upload:
                await upload.write(b"half")
                raise RuntimeError("upstream broke")
        assert list(await db.scalars(select(Blob))) == []
    assert [item async for item in storage.iterate()] == []
    assert list((app.state.settings.storage_path / ".tmp").iterdir()) == []


async def test_upload_refused_when_space_is_low(app: FastAPI, blobs, store_id, monkeypatch) -> None:
    async def low_usage(self):
        return StorageUsage(total_bytes=100 * GiB, free_bytes=1 * GiB)

    monkeypatch.setattr(FilesystemBlobStorage, "usage", low_usage)
    async with app.state.db_sessionmaker() as db:
        with pytest.raises(StorageFullError):
            await blobs.upload(db, store_id)


async def run_job(app: FastAPI, job_type: str) -> Job:
    async with app.state.db_sessionmaker() as db:
        job = await enqueue(db, job_type)
        await db.commit()
    await app.state.job_runner.run_pending()
    async with app.state.db_sessionmaker() as db:
        return await db.get(Job, job.id)


async def test_blob_gc_respects_grace_period(app: FastAPI, blobs, store_id) -> None:
    live = await create_blob(app, blobs, store_id, b"live")
    recent = await create_blob(app, blobs, store_id, b"recently deleted")
    expired = await create_blob(app, blobs, store_id, b"deleted long ago")
    now = datetime.now(UTC)
    async with app.state.db_sessionmaker() as db:
        await db.execute(update(Blob).where(Blob.id == recent.id).values(deleted_at=now))
        await db.execute(
            update(Blob).where(Blob.id == expired.id).values(deleted_at=now - timedelta(days=2))
        )
        await db.commit()

    job = await run_job(app, BLOB_GC_JOB)
    assert job.status == "succeeded"
    assert job.result == {"removed": 1, "removed_bytes": len(b"deleted long ago")}

    storage = FilesystemBlobStorage(app.state.settings.storage_path)
    async with app.state.db_sessionmaker() as db:
        remaining = set(await db.scalars(select(Blob.id)))
    assert remaining == {live.id, recent.id}
    assert await storage.stat(expired.id) is None
    assert await storage.stat(recent.id) is not None


async def test_store_cleanup_removes_old_orphans_only(app: FastAPI, blobs, store_id) -> None:
    storage = FilesystemBlobStorage(app.state.settings.storage_path)
    known = await create_blob(app, blobs, store_id, b"known")
    make_old(storage.path_for(known.id))

    async def write_orphan(age: timedelta | None) -> uuid.UUID:
        blob_id = uuid.uuid4()
        writer = await storage.open_write(blob_id)
        await writer.write(b"orphan")
        await writer.commit()
        if age:
            make_old(storage.path_for(blob_id), age)
        return blob_id

    old_orphan = await write_orphan(timedelta(days=2))
    young_orphan = await write_orphan(None)
    stale_temp = storage.temp_dir / "stale.part"
    stale_temp.write_bytes(b"x")
    make_old(stale_temp)

    job = await run_job(app, STORE_CLEANUP_JOB)
    assert job.status == "succeeded", job.error
    assert job.result == {
        "checked": 3,
        "orphans_removed": 1,
        "orphan_bytes": len(b"orphan"),
        "temp_removed": 1,
    }
    assert await storage.stat(old_orphan) is None
    assert await storage.stat(young_orphan) is not None
    assert await storage.stat(known.id) is not None


async def test_blob_stores_api(app: FastAPI, api, create_user, blobs, store_id) -> None:
    await create_user("root", roles=("admin",))
    await api.login("root", "password123")
    await create_blob(app, blobs, store_id, b"12345")
    deleted = await create_blob(app, blobs, store_id, b"123")
    async with app.state.db_sessionmaker() as db:
        await db.execute(
            update(Blob).where(Blob.id == deleted.id).values(deleted_at=datetime.now(UTC))
        )
        await db.commit()

    stores = (await api.get("/api/v1/blob-stores")).json()
    assert len(stores) == 1
    store = stores[0]
    assert (store["name"], store["type"]) == ("default", "filesystem")
    assert (store["blob_count"], store["used_bytes"]) == (1, 5)
    assert (store["pending_delete_count"], store["pending_delete_bytes"]) == (1, 3)
    assert store["total_bytes"] > 0 and store["free_bytes"] > 0
    assert (await api.get(f"/api/v1/blob-stores/{store_id}")).json()["id"] == store_id
    response = await api.get("/api/v1/blob-stores/999")
    assert response.json()["error"]["code"] == "blob_store_not_found"
