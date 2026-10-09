"""Moving blobs between blob stores (job `blob_migrate`).

Each blob is copied under the same id, verified by size and sha256, switched to the
target store in the database and then removed from the source. Reads that are already
in progress keep working (open files on Linux survive unlink). Blobs written to the
source while the job runs are picked up by repeated passes.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from repoman.db.models import Blob
from repoman.jobs.runner import JobContext, JobFailed
from repoman.storage.base import BlobNotFoundError, StorageFullError
from repoman.storage.service import BlobService

BATCH_SIZE = 100
MAX_PASSES = 10


async def blob_migrate(ctx: JobContext) -> dict[str, Any]:
    service: BlobService = ctx.services["blobs"]
    source_id = int(ctx.params["source_store_id"])
    target_id = int(ctx.params["target_store_id"])
    # A repository-scoped migration (added with repositories) narrows the blob set.
    state = ctx.checkpoint or {"moved": 0, "moved_bytes": 0, "skipped": [], "cursor": None}
    skipped: set[str] = set(state["skipped"])

    for _ in range(MAX_PASSES):
        moved_in_pass = 0
        cursor: str | None = state["cursor"]
        async with ctx.sessionmaker() as db:
            remaining = await db.scalar(
                select(func.count(Blob.id)).where(
                    Blob.blob_store_id == source_id, Blob.deleted_at.is_(None)
                )
            )
        await ctx.progress(state["moved"], state["moved"] + int(remaining or 0))

        while True:
            await ctx.check_cancelled()
            async with ctx.sessionmaker() as db:
                query = (
                    select(Blob)
                    .where(Blob.blob_store_id == source_id, Blob.deleted_at.is_(None))
                    .order_by(Blob.id)
                    .limit(BATCH_SIZE)
                )
                if cursor:
                    query = query.where(Blob.id > UUID(cursor))
                batch = list(await db.scalars(query))
            if not batch:
                break
            for blob in batch:
                cursor = str(blob.id)
                if cursor in skipped:
                    continue
                if await _move(ctx, service, blob, target_id):
                    state["moved"] += 1
                    state["moved_bytes"] += blob.size
                    moved_in_pass += 1
                else:
                    skipped.add(cursor)
            state.update(cursor=cursor, skipped=sorted(skipped))
            await ctx.save_checkpoint(state)
            await ctx.progress(state["moved"])
        state["cursor"] = None
        await ctx.save_checkpoint(state)
        if moved_in_pass == 0:
            break

    await ctx.log(
        f"Moved {state['moved']} blobs ({state['moved_bytes']} bytes), skipped {len(skipped)}"
    )
    if skipped:
        raise JobFailed(
            f"{len(skipped)} blobs could not be moved (see the log); the rest were moved"
        )
    return {"moved": state["moved"], "moved_bytes": state["moved_bytes"], "skipped": 0}


async def _move(ctx: JobContext, service: BlobService, blob: Blob, target_id: int) -> bool:
    """Move one blob. Returns False if it was skipped (reported in the job log)."""
    async with ctx.sessionmaker() as db:
        source = await service.storage(db, blob.blob_store_id)
        try:
            stream = await source.open_read(blob.id)
        except BlobNotFoundError:
            await ctx.log(f"Blob {blob.id} is missing in the source store", "error")
            return False
        try:
            upload = await service.upload(db, target_id, blob_id=blob.id)
        except StorageFullError as exc:
            raise JobFailed(f"Target store cannot accept data: {exc}") from None
        async with upload:
            async for chunk in stream:
                await upload.write(chunk)
            if upload.size != blob.size or upload.sha256 != blob.sha256:
                await ctx.log(f"Blob {blob.id}: size or checksum mismatch, not moved", "error")
                return False
            await upload.finish()

        result = await db.execute(
            update(Blob)
            .where(
                Blob.id == blob.id,
                Blob.blob_store_id == blob.blob_store_id,
                Blob.deleted_at.is_(None),
            )
            .values(blob_store_id=target_id)
        )
        await db.commit()

    if result.rowcount == 0:
        # Deleted while being copied: it stays in the source until garbage collection.
        await (await _storage(ctx, service, target_id)).delete(blob.id)
        return True
    await source.delete(blob.id)
    return True


async def _storage(ctx: JobContext, service: BlobService, store_id: int):
    async with ctx.sessionmaker() as db:
        return await service.storage(db, store_id)
