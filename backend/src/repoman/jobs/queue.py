"""Job queue on PostgreSQL (design §10).

Jobs are claimed with SELECT ... FOR UPDATE SKIP LOCKED. A job that stops sending
heartbeats (e.g. the process died) is returned to the queue and resumes from its
checkpoint, up to max_attempts.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.db.models import Job, JobLog
from repoman.errors import ApiError


def _now() -> datetime:
    return datetime.now(UTC)


async def enqueue(
    db: AsyncSession,
    job_type: str,
    *,
    params: dict[str, Any] | None = None,
    resource_key: str | None = None,
    created_by_id: int | None = None,
) -> Job:
    """Add a job in the current transaction (committed by the caller).

    Raises ApiError 409 `job_already_active` if an active job holds the same resource_key.
    """
    job = Job(
        type=job_type,
        params=params or {},
        resource_key=resource_key,
        created_by_id=created_by_id,
        status="queued",
        scheduled_at=_now(),
    )
    try:
        async with db.begin_nested():
            db.add(job)
    except IntegrityError:
        raise ApiError(
            409,
            "job_already_active",
            "A job for this resource is already queued or running",
            {"resource_key": resource_key},
        ) from None
    return job


async def claim(db: AsyncSession) -> Job | None:
    job = await db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.scheduled_at <= _now())
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    now = _now()
    job.status = "running"
    job.attempts += 1
    job.started_at = job.started_at or now
    job.heartbeat_at = now
    await db.commit()
    return job


async def recover_stale(db: AsyncSession, stale_after: timedelta) -> None:
    """Return jobs of a dead worker to the queue (or fail them when out of attempts)."""
    threshold = _now() - stale_after
    stale = (Job.status == "running", Job.heartbeat_at < threshold)
    await db.execute(
        update(Job)
        .where(*stale, Job.attempts < Job.max_attempts)
        .values(status="queued", scheduled_at=_now())
    )
    await db.execute(
        update(Job)
        .where(*stale, Job.attempts >= Job.max_attempts)
        .values(status="failed", error="Worker stopped responding", finished_at=_now())
    )
    await db.commit()


async def add_log(db: AsyncSession, job_id: int, level: str, message: str) -> None:
    db.add(JobLog(job_id=job_id, level=level, message=message))
