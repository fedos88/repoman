from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    # Endpoints commit explicitly; anything not committed is rolled back on close.
    async with request.app.state.db_sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
