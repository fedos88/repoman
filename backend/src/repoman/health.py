import asyncio
import logging
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

CheckStatus = Literal["ok", "fail"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


async def _check_database(request: Request) -> CheckStatus:
    try:
        async with request.app.state.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # readiness reports any failure instead of raising
        logger.warning("Readiness: database check failed: %s", type(exc).__name__)
        return "fail"
    return "ok"


def _probe_storage(storage_path: Path) -> None:
    tmp_dir = storage_path / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    probe = tmp_dir / f"readyz-{uuid.uuid4().hex}"
    probe.write_bytes(b"ok")
    probe.unlink()


async def _check_storage(request: Request) -> CheckStatus:
    try:
        await asyncio.to_thread(_probe_storage, request.app.state.settings.storage_path)
    except OSError as exc:
        logger.warning("Readiness: storage check failed: %s", exc)
        return "fail"
    return "ok"


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readyz(request: Request) -> JSONResponse:
    checks: dict[str, CheckStatus] = {
        "database": await _check_database(request),
        "storage": await _check_storage(request),
    }
    ready = all(status == "ok" for status in checks.values())
    body = ReadinessResponse(status="ok" if ready else "fail", checks=checks)
    return JSONResponse(status_code=200 if ready else 503, content=body.model_dump())
