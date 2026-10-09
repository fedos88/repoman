from datetime import UTC, datetime

from fastapi import Request, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.auth.policy import CSRF_COOKIE, SESSION_ABSOLUTE_TIMEOUT, SESSION_COOKIE
from repoman.auth.security import hash_secret, new_secret
from repoman.db.models import AuthSession, User


def client_ip(request: Request) -> str:
    # Already resolved from X-Forwarded-For by uvicorn for trusted proxies only.
    return request.client.host if request.client else "unknown"


async def create_session(db: AsyncSession, user: User, request: Request) -> tuple[str, AuthSession]:
    session_id = new_secret()
    now = datetime.now(UTC)
    session = AuthSession(
        id_hash=hash_secret(session_id),
        user_id=user.id,
        csrf_token=new_secret(),
        last_seen_at=now,
        expires_at=now + SESSION_ABSOLUTE_TIMEOUT,
        ip=client_ip(request)[:64],
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
    )
    db.add(session)
    return session_id, session


def set_session_cookies(
    response: Response, request: Request, session_id: str, session: AuthSession
) -> None:
    secure = request.url.scheme == "https"
    max_age = int(SESSION_ABSOLUTE_TIMEOUT.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Readable by the SPA, which echoes it in the X-CSRF-Token header (double submit).
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def delete_user_sessions(
    db: AsyncSession, user_id: int, keep_id_hash: str | None = None
) -> None:
    statement = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_id_hash is not None:
        statement = statement.where(AuthSession.id_hash != keep_id_hash)
    await db.execute(statement)
