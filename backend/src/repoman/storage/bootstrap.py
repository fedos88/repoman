import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from repoman.config import Settings
from repoman.db.models import BlobStore
from repoman.jobs.schedules import ensure_schedule
from repoman.storage.policy import (
    BLOB_GC_INTERVAL_SECONDS,
    BLOB_GC_JOB,
    DEFAULT_STORE_NAME,
    STORE_CLEANUP_INTERVAL_SECONDS,
    STORE_CLEANUP_JOB,
)

logger = logging.getLogger(__name__)


async def ensure_default_store(sessionmaker: async_sessionmaker, settings: Settings) -> int:
    """Create or update the default filesystem store from REPOMAN_STORAGE_PATH."""
    path = str(settings.storage_path.resolve())
    async with sessionmaker() as db:
        store = await db.scalar(select(BlobStore).where(BlobStore.name == DEFAULT_STORE_NAME))
        if store is None:
            store = BlobStore(name=DEFAULT_STORE_NAME, type="filesystem", config={"path": path})
            db.add(store)
            logger.info("Created default blob store at %s", path)
        elif store.config.get("path") != path:
            logger.warning(
                "Default blob store path changed: %s -> %s", store.config.get("path"), path
            )
            store.config = {**store.config, "path": path}
        await ensure_schedule(db, BLOB_GC_JOB, BLOB_GC_INTERVAL_SECONDS)
        await ensure_schedule(db, STORE_CLEANUP_JOB, STORE_CLEANUP_INTERVAL_SECONDS)
        await db.commit()
        return store.id
