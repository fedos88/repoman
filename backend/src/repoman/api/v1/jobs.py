from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from repoman.auth.dependencies import AdminPrincipal
from repoman.db.deps import DbSession
from repoman.db.models import Job, JobLog
from repoman.errors import ApiError

router = APIRouter(prefix="/jobs", tags=["jobs"])

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobOut(BaseModel):
    id: int
    type: str
    resource_key: str | None
    status: JobStatus
    params: dict[str, Any]
    result: dict[str, Any] | None
    progress_done: int
    progress_total: int | None
    attempts: int
    error: str | None
    cancel_requested: bool
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, job: Job) -> "JobOut":
        return cls(
            id=job.id,
            type=job.type,
            resource_key=job.resource_key,
            status=job.status,  # type: ignore[arg-type]
            params=job.params or {},
            result=job.result,
            progress_done=job.progress_done or 0,
            progress_total=job.progress_total,
            attempts=job.attempts or 0,
            error=job.error,
            cancel_requested=bool(job.cancel_requested),
            created_by_id=job.created_by_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class JobPage(BaseModel):
    items: list[JobOut]
    total: int


class JobLogOut(BaseModel):
    ts: datetime
    level: str
    message: str


async def get_job_or_404(db: DbSession, job_id: int) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise ApiError(404, "job_not_found", "Job not found")
    return job


@router.get("", response_model=JobPage)
async def list_jobs(
    _: AdminPrincipal,
    db: DbSession,
    type: Annotated[str | None, Query(max_length=64)] = None,
    status: JobStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    conditions = []
    if type:
        conditions.append(Job.type == type)
    if status:
        conditions.append(Job.status == status)
    total = int(await db.scalar(select(func.count(Job.id)).where(*conditions)) or 0)
    jobs = await db.scalars(
        select(Job).where(*conditions).order_by(Job.id.desc()).limit(limit).offset(offset)
    )
    return JobPage(items=[JobOut.of(job) for job in jobs], total=total)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, _: AdminPrincipal, db: DbSession) -> JobOut:
    return JobOut.of(await get_job_or_404(db, job_id))


@router.get("/{job_id}/logs", response_model=list[JobLogOut])
async def get_job_logs(job_id: int, _: AdminPrincipal, db: DbSession) -> list[JobLogOut]:
    await get_job_or_404(db, job_id)
    logs = await db.scalars(select(JobLog).where(JobLog.job_id == job_id).order_by(JobLog.id))
    return [JobLogOut(ts=log.ts, level=log.level, message=log.message) for log in logs]


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: int, _: AdminPrincipal, db: DbSession) -> JobOut:
    job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise ApiError(404, "job_not_found", "Job not found")
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
    elif job.status == "running":
        job.cancel_requested = True
    else:
        raise ApiError(409, "job_not_cancellable", "Job has already finished")
    await db.commit()
    return JobOut.of(job)
