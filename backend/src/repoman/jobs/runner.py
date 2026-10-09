"""In-process job worker and scheduler (single-process deployment, design §2, §10)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from repoman.db.models import Job, Schedule
from repoman.errors import ApiError
from repoman.jobs.queue import add_log, claim, enqueue, recover_stale

logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobFailed(Exception):
    """Expected failure with a message for the job log (no traceback)."""


@dataclass
class JobContext:
    job_id: int
    job_type: str
    params: dict[str, Any]
    checkpoint: dict[str, Any] | None
    sessionmaker: async_sessionmaker
    services: dict[str, Any] = field(default_factory=dict)

    async def log(self, message: str, level: str = "info") -> None:
        async with self.sessionmaker() as db:
            await add_log(db, self.job_id, level, message)
            await db.commit()

    async def progress(self, done: int, total: int | None = None) -> None:
        values: dict[str, Any] = {"progress_done": done, "heartbeat_at": datetime.now(UTC)}
        if total is not None:
            values["progress_total"] = total
        await self._update(values)

    async def save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self.checkpoint = checkpoint
        await self._update({"checkpoint": checkpoint, "heartbeat_at": datetime.now(UTC)})

    async def check_cancelled(self) -> None:
        async with self.sessionmaker() as db:
            if await db.scalar(select(Job.cancel_requested).where(Job.id == self.job_id)):
                raise JobCancelled

    async def _update(self, values: dict[str, Any]) -> None:
        async with self.sessionmaker() as db:
            await db.execute(update(Job).where(Job.id == self.job_id).values(**values))
            await db.commit()


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


class JobRunner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        handlers: dict[str, Handler],
        *,
        services: dict[str, Any] | None = None,
        poll_interval: float = 2.0,
        heartbeat_interval: float = 15.0,
        stale_after: timedelta = timedelta(minutes=2),
        schedule_interval: float = 30.0,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.handlers = handlers
        self.services = services or {}
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.stale_after = stale_after
        self.schedule_interval = schedule_interval
        self._wakeup = asyncio.Event()

    def wake(self) -> None:
        """Process newly enqueued jobs without waiting for the next poll."""
        self._wakeup.set()

    # --- worker ---------------------------------------------------------------------------

    async def run_once(self) -> bool:
        """Run one queued job, if any. Returns True if a job was processed."""
        async with self.sessionmaker() as db:
            job = await claim(db)
        if job is None:
            return False
        await self._execute(job)
        return True

    async def run_pending(self) -> None:
        while await self.run_once():
            pass

    async def _execute(self, job: Job) -> None:
        handler = self.handlers.get(job.type)
        ctx = JobContext(
            job_id=job.id,
            job_type=job.type,
            params=dict(job.params or {}),
            checkpoint=job.checkpoint,
            sessionmaker=self.sessionmaker,
            services=self.services,
        )
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        status, result, error = "succeeded", None, None
        try:
            if handler is None:
                raise JobFailed(f"Unknown job type: {job.type}")
            await ctx.log(f"Started (attempt {job.attempts})")
            result = await handler(ctx)
        except JobCancelled:
            status = "cancelled"
            await ctx.log("Cancelled", "warning")
        except JobFailed as exc:
            status, error = "failed", str(exc)
            await ctx.log(error, "error")
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.type)
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            await ctx.log(error, "error")
        finally:
            heartbeat.cancel()
        async with self.sessionmaker() as db:
            await db.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(status=status, result=result, error=error, finished_at=datetime.now(UTC))
            )
            await add_log(db, job.id, "info", f"Finished: {status}")
            await db.commit()

    async def _heartbeat(self, job_id: int) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            async with self.sessionmaker() as db:
                await db.execute(
                    update(Job).where(Job.id == job_id).values(heartbeat_at=datetime.now(UTC))
                )
                await db.commit()

    async def worker_loop(self) -> None:
        while True:
            try:
                async with self.sessionmaker() as db:
                    await recover_stale(db, self.stale_after)
                while await self.run_once():
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Job worker iteration failed")
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    # --- scheduler ------------------------------------------------------------------------

    async def schedule_due(self) -> None:
        """Enqueue jobs whose schedule is due (resource_key = job type: one active at a time)."""
        now = datetime.now(UTC)
        async with self.sessionmaker() as db:
            schedules = await db.scalars(
                select(Schedule)
                .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            )
            enqueued = False
            for schedule in schedules:
                schedule.next_run_at = now + timedelta(seconds=schedule.interval_seconds)
                try:
                    await enqueue(db, schedule.job_type, resource_key=schedule.job_type)
                    enqueued = True
                except ApiError:
                    logger.info("Scheduled %s skipped: already active", schedule.job_type)
            await db.commit()
        if enqueued:
            self.wake()

    async def scheduler_loop(self) -> None:
        while True:
            try:
                await self.schedule_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Job scheduler iteration failed")
            await asyncio.sleep(self.schedule_interval)
