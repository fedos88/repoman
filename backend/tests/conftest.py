import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from repoman.auth.policy import CSRF_COOKIE, CSRF_HEADER
from repoman.auth.security import hash_password
from repoman.config import Settings
from repoman.db.migrate import upgrade_to_head
from repoman.db.models import Role, User, UserRole
from repoman.db.session import create_engine
from repoman.main import create_app
from tests.fakes import FakeDirectory

# Nothing listens on port 1: database checks fail fast without external dependencies.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://repoman:repoman@127.0.0.1:1/repoman"
SECRET_KEY = "test-secret-key-test-secret-key-0000"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=UNREACHABLE_DATABASE_URL,
        storage_path=tmp_path / "storage",
        secret_key=SECRET_KEY,
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    await app.state.db_engine.dispose()


# --- Tests with a real PostgreSQL (REPOMAN_TEST_DATABASE_URL) ---------------------------


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("REPOMAN_TEST_DATABASE_URL")
    if not url:
        pytest.skip("REPOMAN_TEST_DATABASE_URL is not set")
    return Settings(database_url=url, storage_path=Path("."), secret_key=SECRET_KEY).database_url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> Iterator[str]:
    """Recreate the schema once per test session and apply all migrations."""

    async def reset() -> None:
        engine = create_engine(database_url)
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    upgrade_to_head(database_url)
    yield database_url


@pytest.fixture
async def app(migrated_database: str, tmp_path: Path) -> AsyncIterator[FastAPI]:
    app = create_app(
        Settings(
            database_url=migrated_database,
            storage_path=tmp_path / "storage",
            secret_key=SECRET_KEY,
        )
    )
    async with app.state.db_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE users, user_roles, sessions, api_tokens, jobs, job_logs, schedules, "
                "ldap_settings, ldap_group_mappings RESTART IDENTITY CASCADE"
            )
        )
    yield app
    await app.state.db_engine.dispose()


class Api(httpx.AsyncClient):
    """Test client that echoes the CSRF cookie like the SPA does."""

    async def request(self, method: str, url: httpx.URL | str, **kwargs):  # type: ignore[override]
        csrf = self.cookies.get(CSRF_COOKIE)
        if csrf and method.upper() not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault(CSRF_HEADER, csrf)
            kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)

    async def login(self, username: str, password: str) -> httpx.Response:
        response = await self.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, response.text
        return response


@pytest.fixture
def make_api(app: FastAPI):
    """Independent clients (separate cookie jars) for the same application."""

    def factory() -> Api:
        return Api(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

    return factory


@pytest.fixture
def api(make_api) -> Api:
    return make_api()


@pytest.fixture
def create_user(app: FastAPI):
    async def factory(
        username: str,
        password: str = "password123",
        *,
        roles: tuple[str, ...] = (),
        auth_source: str = "local",
        is_active: bool = True,
        must_change_password: bool = False,
    ) -> User:
        async with app.state.db_sessionmaker() as db:
            user = User(
                username=username,
                auth_source=auth_source,
                password_hash=await hash_password(password) if auth_source == "local" else None,
                must_change_password=must_change_password,
                is_active=is_active,
                roles=[],
            )
            for name in roles:
                role = await db.scalar(select(Role).where(Role.name == name))
                user.roles.append(UserRole(role=role, source="manual"))
            db.add(user)
            await db.commit()
            return user

    return factory


@pytest.fixture
def directory(app: FastAPI) -> FakeDirectory:
    """Replaces the LDAP directory of the application with an in-memory fake."""
    fake = FakeDirectory()
    app.state.ldap.factory = fake.factory
    return fake
