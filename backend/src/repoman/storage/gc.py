"""Jobs removing deleted blobs and orphaned objects (design §7.5)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from repoman.db.models import Blob, BlobStore
from repoman.jobs.runner import JobContext
from repoman.storage.base import BlobStat, BlobStorage
from repoman.storage.policy import GC_GRACE_PERIOD, ORPHAN_MIN_AGE
from repoman.storage.service import BlobService

BATCH_SIZE = 500


async def blob_gc(ctx: JobContext) -> dict[str, Any]:
    """Physically remove blobs deleted more than the grace period ago."""
    service: BlobService = ctx.services["blobs"]
    threshold = datetime.now(UTC) - GC_GRACE_PERIOD
    removed = removed_bytes = 0
    while True:
        await ctx.check_cancelled()
        async with ctx.sessionmaker() as db:
            batch = list(
                await db.scalars(
                    select(Blob)
                    .where(Blob.deleted_at.is_not(None), Blob.deleted_at < threshold)
                    .order_by(Blob.deleted_at)
                    .limit(BATCH_SIZE)
                )
            )
            if not batch:
                break
            for blob in batch:
                storage = await service.storage(db, blob.blob_store_id)
                await storage.delete(blob.id)
                removed_bytes += blob.size
            await db.execute(delete(Blob).where(Blob.id.in_([blob.id for blob in batch])))
            await db.commit()
        removed += len(batch)
        await ctx.progress(removed)
    if removed:
        await ctx.log(f"Removed {removed} blobs, {removed_bytes} bytes")
    return {"removed": removed, "removed_bytes": removed_bytes}


async def blob_store_cleanup(ctx: JobContext) -> dict[str, Any]:
    """Remove abandoned temporary files and objects without a database row."""
    service: BlobService = ctx.services["blobs"]
    threshold = datetime.now(UTC) - ORPHAN_MIN_AGE
    stats = {"checked": 0, "orphans_removed": 0, "orphan_bytes": 0, "temp_removed": 0}
    async with ctx.sessionmaker() as db:
        store_ids = list(await db.scalars(select(BlobStore.id).order_by(BlobStore.id)))

    for store_id in store_ids:
        async with ctx.sessionmaker() as db:
            storage = await service.storage(db, store_id)
        stats["temp_removed"] += await storage.cleanup_temp(ORPHAN_MIN_AGE)

        candidates = []
        async for item in storage.iterate():
            stats["checked"] += 1
            if item.modified_at < threshold:
                candidates.append(item)
            if len(candidates) >= BATCH_SIZE:
                await _remove_orphans(ctx, store_id, storage, candidates, stats)
                candidates = []
        await _remove_orphans(ctx, store_id, storage, candidates, stats)
        await ctx.progress(stats["checked"])

    await ctx.log(
        "Checked {checked} objects, removed {orphans_removed} orphans "
        "({orphan_bytes} bytes) and {temp_removed} temporary files".format(**stats)
    )
    return stats


async def _remove_orphans(
    ctx: JobContext,
    store_id: int,
    storage: BlobStorage,
    candidates: list[BlobStat],
    stats: dict[str, int],
) -> None:
    if not candidates:
        return
    await ctx.check_cancelled()
    async with ctx.sessionmaker() as db:
        # A blob belongs to exactly one store: a copy left in another store
        # (e.g. by an interrupted migration) is an orphan there.
        known = set(
            await db.scalars(
                select(Blob.id).where(
                    Blob.blob_store_id == store_id,
                    Blob.id.in_([c.blob_id for c in candidates]),
                )
            )
        )
    for item in candidates:
        if item.blob_id not in known:
            await storage.delete(item.blob_id)
            stats["orphans_removed"] += 1
            stats["orphan_bytes"] += item.size
