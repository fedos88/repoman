import hashlib
import os
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from repoman.db.models import Blob, BlobStore, Job, Schedule
from repoman.jobs.queue import enqueue
from repoman.storage.base import (
    BlobNotFoundError,
    QuotaExceededError,
    StorageFullError,
    StorageUsage,
)
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


# --- blob store management ----------------------------------------------------------------


@pytest.fixture
async def admin_api(api, create_user, store_id):
    await create_user("root", roles=("admin",))
    await api.login("root", "password123")
    return api


async def add_store(admin_api, name: str, path: Path, **extra) -> dict:
    response = await admin_api.post(
        "/api/v1/blob-stores", json={"name": name, "path": str(path), **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_store_and_validation(app: FastAPI, admin_api, tmp_path: Path) -> None:
    disk2 = tmp_path / "disk2" / "repoman"
    store = await add_store(admin_api, " Disk2 ", disk2, quota_bytes=1024)
    assert (store["name"], store["type"], store["is_default"]) == ("disk2", "filesystem", False)
    assert store["path"] == str(disk2.resolve()) and disk2.is_dir()  # created
    assert store["available"] is True and store["quota_bytes"] == 1024

    default_path = app.state.settings.storage_path
    a_file = tmp_path / "file"
    a_file.write_text("x")
    cases = [
        ({"name": "disk2", "path": str(tmp_path / "other")}, "blob_store_name_taken"),
        ({"name": "bad name", "path": str(tmp_path / "other")}, "validation_error"),
        ({"name": "rel", "path": "relative/path"}, "blob_store_path_invalid"),
        ({"name": "same", "path": str(default_path)}, "blob_store_path_overlap"),
        ({"name": "nested", "path": str(default_path / "sub")}, "blob_store_path_overlap"),
        ({"name": "parent", "path": str(tmp_path / "disk2")}, "blob_store_path_overlap"),
        ({"name": "nowrite", "path": str(a_file / "sub")}, "blob_store_path_not_writable"),
    ]
    for body, code in cases:
        response = await admin_api.post("/api/v1/blob-stores", json=body)
        assert response.json()["error"]["code"] == code, body


async def test_update_and_delete_rules(app, admin_api, blobs, store_id, tmp_path: Path) -> None:
    store = await add_store(admin_api, "disk2", tmp_path / "disk2")
    url = f"/api/v1/blob-stores/{store['id']}"

    body = (await admin_api.patch(url, json={"name": "fast", "quota_bytes": 10})).json()
    assert (body["name"], body["quota_bytes"]) == ("fast", 10)
    assert (await admin_api.patch(url, json={"quota_bytes": None})).json()["quota_bytes"] is None
    moved = (await admin_api.patch(url, json={"path": str(tmp_path / "disk3")})).json()
    assert moved["path"] == str((tmp_path / "disk3").resolve())

    await create_blob(app, blobs, store["id"], b"data")
    response = await admin_api.patch(url, json={"path": str(tmp_path / "disk4")})
    assert response.json()["error"]["code"] == "blob_store_not_empty"
    assert (await admin_api.delete(url)).json()["error"]["code"] == "blob_store_not_empty"

    default_url = f"/api/v1/blob-stores/{store_id}"
    for body in ({"name": "main"}, {"path": str(tmp_path / "x")}):
        response = await admin_api.patch(default_url, json=body)
        assert response.json()["error"]["code"] == "blob_store_is_default"
    assert (await admin_api.patch(default_url, json={"quota_bytes": 5})).status_code == 200
    response = await admin_api.delete(default_url)
    assert response.json()["error"]["code"] == "blob_store_is_default"

    empty = await add_store(admin_api, "empty", tmp_path / "empty")
    assert (await admin_api.delete(f"/api/v1/blob-stores/{empty['id']}")).status_code == 204
    assert (tmp_path / "empty").is_dir()  # files on disk are not touched


async def test_check_does_not_create_missing_directory(admin_api, tmp_path: Path) -> None:
    store = await add_store(admin_api, "disk2", tmp_path / "disk2")
    url = f"/api/v1/blob-stores/{store['id']}"
    assert (await admin_api.post(f"{url}/check")).json()["ok"] is True

    shutil.rmtree(tmp_path / "disk2")  # e.g. the bind mount is gone
    result = (await admin_api.post(f"{url}/check")).json()
    assert (result["ok"], result["error_code"]) == (False, "blob_store_path_missing")
    assert not (tmp_path / "disk2").exists()
    assert (await admin_api.get(url)).json()["available"] is False


async def test_quota_blocks_new_blobs(app, admin_api, blobs, store_id) -> None:
    await admin_api.patch(f"/api/v1/blob-stores/{store_id}", json={"quota_bytes": 10})
    await create_blob(app, blobs, store_id, b"0123456789")  # reaches the quota
    blobs.forget(store_id)  # drop the cached stored size
    async with app.state.db_sessionmaker() as db:
        with pytest.raises(QuotaExceededError):
            await blobs.upload(db, store_id)
    store = (await admin_api.get(f"/api/v1/blob-stores/{store_id}")).json()
    assert store["quota_exceeded"] is True


async def test_migrate_all_blobs(app, admin_api, blobs, store_id, tmp_path: Path) -> None:
    payloads = [f"blob {i}".encode() * 100 for i in range(5)]
    created = [await create_blob(app, blobs, store_id, data) for data in payloads]
    deleted = await create_blob(app, blobs, store_id, b"pending deletion")
    async with app.state.db_sessionmaker() as db:
        await db.execute(
            update(Blob).where(Blob.id == deleted.id).values(deleted_at=datetime.now(UTC))
        )
        await db.commit()
    target = await add_store(admin_api, "disk2", tmp_path / "disk2")
    migrate_url = f"/api/v1/blob-stores/{store_id}/migrate"

    response = await admin_api.post(migrate_url, json={"target_store_id": target["id"]})
    assert response.status_code == 202
    again = await admin_api.post(migrate_url, json={"target_store_id": target["id"]})
    assert again.json()["error"]["code"] == "job_already_active"
    busy = await admin_api.delete(f"/api/v1/blob-stores/{target['id']}")
    assert busy.json()["error"]["code"] == "blob_store_in_use"
    same = await admin_api.post(migrate_url, json={"target_store_id": store_id})
    assert same.json()["error"]["code"] == "blob_store_same"

    await app.state.job_runner.run_pending()
    async with app.state.db_sessionmaker() as db:
        job = await db.scalar(select(Job).order_by(Job.id.desc()).limit(1))
        assert job.status == "succeeded", job.error
        assert job.result["moved"] == 5
        rows = {b.id: b for b in await db.scalars(select(Blob))}
        for blob, data in zip(created, payloads, strict=True):
            assert rows[blob.id].blob_store_id == target["id"]
            assert await read_all(await blobs.read(db, rows[blob.id])) == data
        assert rows[deleted.id].blob_store_id == store_id  # left for garbage collection

    source = FilesystemBlobStorage(app.state.settings.storage_path)
    assert [item.blob_id async for item in source.iterate()] == [deleted.id]


async def test_migrate_reports_missing_source_objects(
    app, admin_api, blobs, store_id, tmp_path: Path
) -> None:
    good = await create_blob(app, blobs, store_id, b"good")
    lost = await create_blob(app, blobs, store_id, b"lost")
    await FilesystemBlobStorage(app.state.settings.storage_path).delete(lost.id)
    target = await add_store(admin_api, "disk2", tmp_path / "disk2")
    await admin_api.post(
        f"/api/v1/blob-stores/{store_id}/migrate", json={"target_store_id": target["id"]}
    )
    await app.state.job_runner.run_pending()
    async with app.state.db_sessionmaker() as db:
        job = await db.scalar(select(Job).order_by(Job.id.desc()).limit(1))
        assert job.status == "failed" and "1 blobs could not be moved" in job.error
        assert (await db.get(Blob, good.id)).blob_store_id == target["id"]
        assert (await db.get(Blob, lost.id)).blob_store_id == store_id


async def test_cleanup_treats_copies_in_other_stores_as_orphans(
    app, admin_api, blobs, store_id, tmp_path: Path
) -> None:
    blob = await create_blob(app, blobs, store_id, b"original")
    await add_store(admin_api, "disk2", tmp_path / "disk2")
    stray = FilesystemBlobStorage(tmp_path / "disk2")
    writer = await stray.open_write(blob.id)  # e.g. left by an interrupted migration
    await writer.write(b"original")
    await writer.commit()
    make_old(stray.path_for(blob.id))
    make_old(FilesystemBlobStorage(app.state.settings.storage_path).path_for(blob.id))

    job = await run_job(app, STORE_CLEANUP_JOB)
    assert job.result["orphans_removed"] == 1
    assert await stray.stat(blob.id) is None
