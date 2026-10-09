import asyncio

from alembic import context
from sqlalchemy.engine import Connection

import repoman.db.models  # noqa: F401  (registers tables in Base.metadata)
from repoman.config import get_settings
from repoman.db.base import Base
from repoman.db.session import create_engine

target_metadata = Base.metadata


def _database_url() -> str:
    return context.config.attributes.get("database_url") or get_settings().database_url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
