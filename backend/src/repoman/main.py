import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from repoman import __version__, health
from repoman.api import v1
from repoman.auth.ratelimit import LoginRateLimiter
from repoman.config import Settings, get_settings
from repoman.crypto import SecretBox
from repoman.db.session import create_engine, create_sessionmaker
from repoman.docs import install_docs
from repoman.errors import ErrorResponse, install_error_handlers
from repoman.jobs.runner import JobRunner
from repoman.ldap import sync as ldap_sync
from repoman.ldap.service import LdapService
from repoman.users.bootstrap import ensure_admin


class RootInfo(BaseModel):
    name: str
    version: str
    docs: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task] = []
        try:
            await ensure_admin(app.state.db_sessionmaker, settings)
            runner: JobRunner = app.state.job_runner
            tasks = [
                asyncio.create_task(runner.worker_loop(), name="job-worker"),
                asyncio.create_task(runner.scheduler_loop(), name="job-scheduler"),
            ]
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await app.state.db_engine.dispose()

    app = FastAPI(
        title="RepoMan",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        responses={"default": {"model": ErrorResponse}},
    )

    app.state.settings = settings
    app.state.db_engine = create_engine(settings.database_url)
    app.state.db_sessionmaker = create_sessionmaker(app.state.db_engine)
    app.state.login_rate_limiter = LoginRateLimiter()
    app.state.ldap = LdapService(SecretBox(settings.secret_key))
    app.state.job_runner = JobRunner(
        app.state.db_sessionmaker,
        {ldap_sync.JOB_TYPE: ldap_sync.ldap_sync},
        services={"ldap": app.state.ldap},
    )

    install_error_handlers(app)
    install_docs(app)
    app.include_router(health.router)
    app.include_router(v1.router)

    @app.get("/", response_model=RootInfo, tags=["system"])
    async def root() -> RootInfo:
        return RootInfo(name="RepoMan", version=__version__, docs="/api/docs")

    return app
