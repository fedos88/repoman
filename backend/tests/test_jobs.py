from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from repoman.db.models import Job, Schedule
from repoman.errors import ApiError
from repoman.jobs.queue import enqueue, recover_stale
from repoman.jobs.runner import JobContext, JobFailed, JobRunner


def make_runner(app: FastAPI, handlers) -> JobRunner:
    return JobRunner(app.state.db_sessionmaker, handlers, heartbeat_interval=60)


async def add_job(app: FastAPI, job_type: str, **kwargs) -> int:
    async with app.state.db_sessionmaker() as db:
        job = await enqueue(db, job_type, **kwargs)
        await db.commit()
        return job.id


async def get_job(app: FastAPI, job_id: int) -> Job:
    async with app.state.db_sessionmaker() as db:
        return await db.get(Job, job_id)


async def test_job_succeeds_with_progress_and_result(app: FastAPI) -> None:
    async def handler(ctx: JobContext):
        await ctx.progress(1, 2)
        await ctx.save_checkpoint({"cursor": "a"})
        await ctx.log("half way")
        return {"answer": ctx.params["value"] * 2}

    job_id = await add_job(app, "demo", params={"value": 21})
    await make_runner(app, {"demo": handler}).run_pending()

    job = await get_job(app, job_id)
    assert job.status == "succeeded"
    assert job.result == {"answer": 42}
    assert (job.progress_done, job.progress_total) == (1, 2)
    assert job.checkpoint == {"cursor": "a"}
    assert job.attempts == 1 and job.finished_at is not None


async def test_job_failures(app: FastAPI) -> None:
    async def expected(_: JobContext):
        raise JobFailed("nothing to do")

    async def crash(_: JobContext):
        raise RuntimeError("boom")

    first = await add_job(app, "expected")
    second = await add_job(app, "crash")
    third = await add_job(app, "unknown")
    await make_runner(app, {"expected": expected, "crash": crash}).run_pending()

    assert (await get_job(app, first)).error == "nothing to do"
    assert (await get_job(app, second)).error == "RuntimeError: boom"
    assert (await get_job(app, third)).error == "Unknown job type: unknown"
    for job_id in (first, second, third):
        assert (await get_job(app, job_id)).status == "failed"


async def test_one_active_job_per_resource(app: FastAPI) -> None:
    await add_job(app, "demo", resource_key="repository:1")
    with pytest.raises(ApiError) as error:
        await add_job(app, "demo", resource_key="repository:1")
    assert error.value.code == "job_already_active"
    # Other resources and jobs without a resource are not affected.
    await add_job(app, "demo", resource_key="repository:2")
    await add_job(app, "demo")


async def test_cooperative_cancel(app: FastAPI) -> None:
    async def handler(ctx: JobContext):
        async with ctx.sessionmaker() as db:
            await db.execute(update(Job).where(Job.id == ctx.job_id).values(cancel_requested=True))
            await db.commit()
        await ctx.check_cancelled()
        return {"unreachable": True}

    job_id = await add_job(app, "demo")
    await make_runner(app, {"demo": handler}).run_pending()
    job = await get_job(app, job_id)
    assert job.status == "cancelled" and job.result is None


async def test_stale_job_is_requeued_then_failed(app: FastAPI) -> None:
    job_id = await add_job(app, "demo")
    old = datetime.now(UTC) - timedelta(minutes=10)
    async with app.state.db_sessionmaker() as db:
        await db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="running", attempts=1, heartbeat_at=old, checkpoint={"at": 5})
        )
        await db.commit()
        await recover_stale(db, timedelta(minutes=2))
    job = await get_job(app, job_id)
    assert job.status == "queued" and job.checkpoint == {"at": 5}

    async with app.state.db_sessionmaker() as db:
        await db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="running", attempts=3, heartbeat_at=old)
        )
        await db.commit()
        await recover_stale(db, timedelta(minutes=2))
    assert (await get_job(app, job_id)).status == "failed"


async def test_scheduler_enqueues_due_jobs(app: FastAPI) -> None:
    async with app.state.db_sessionmaker() as db:
        db.add(
            Schedule(
                job_type="tick",
                interval_seconds=3600,
                enabled=True,
                next_run_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.add(
            Schedule(
                job_type="later",
                interval_seconds=3600,
                enabled=True,
                next_run_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await db.commit()
    runner = make_runner(app, {})
    await runner.schedule_due()
    await runner.schedule_due()  # not due anymore
    async with app.state.db_sessionmaker() as db:
        jobs = list(await db.scalars(select(Job)))
        schedule = await db.get(Schedule, "tick")
    assert [job.type for job in jobs] == ["tick"]
    assert schedule.next_run_at > datetime.now(UTC) + timedelta(minutes=59)


async def test_jobs_api(app: FastAPI, api, create_user) -> None:
    await create_user("root", roles=("admin",))
    await api.login("root", "password123")

    async def handler(ctx: JobContext):
        await ctx.log("hello")

    done = await add_job(app, "demo")
    await make_runner(app, {"demo": handler}).run_pending()
    queued = await add_job(app, "demo")

    page = (await api.get("/api/v1/jobs", params={"status": "succeeded"})).json()
    assert [j["id"] for j in page["items"]] == [done]
    logs = (await api.get(f"/api/v1/jobs/{done}/logs")).json()
    assert [entry["message"] for entry in logs] == [
        "Started (attempt 1)",
        "hello",
        "Finished: succeeded",
    ]

    assert (await api.post(f"/api/v1/jobs/{queued}/cancel")).json()["status"] == "cancelled"
    response = await api.post(f"/api/v1/jobs/{done}/cancel")
    assert response.json()["error"]["code"] == "job_not_cancellable"
    assert (await api.get("/api/v1/jobs/999")).json()["error"]["code"] == "job_not_found"
