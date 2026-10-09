from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from repoman.db.models import Schedule


async def upsert_schedule(
    db: AsyncSession, job_type: str, interval_seconds: int, *, enabled: bool
) -> Schedule:
    """Create or update a schedule; the next run is one interval from now."""
    schedule = await db.get(Schedule, job_type)
    next_run_at = datetime.now(UTC) + timedelta(seconds=interval_seconds)
    if schedule is None:
        schedule = Schedule(job_type=job_type)
        db.add(schedule)
    if schedule.interval_seconds != interval_seconds or not schedule.enabled:
        schedule.next_run_at = next_run_at
    schedule.interval_seconds = interval_seconds
    schedule.enabled = enabled
    return schedule
