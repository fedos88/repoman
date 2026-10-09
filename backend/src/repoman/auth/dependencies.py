"""Request authentication: API token (Bearer or Basic) or UI session cookie."""

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select

from repoman.auth.policy import (
    ACTIVITY_UPDATE_INTERVAL,
    CSRF_HEADER,
    SAFE_METHODS,
    SESSION_COOKIE,
    SESSION_IDLE_TIMEOUT,
)
from repoman.auth.security import hash_secret, secrets_equal
from repoman.db.deps import DbSession
from repoman.db.models import (
    ROLE_ADMIN,
    ROLE_ANONYMOUS,
    ROLE_AUTHENTICATED,
    ApiToken,
    AuthSession,
    User,
)
from repoman.errors import ApiError
from repoman.users.names import normalize_login


@dataclass
class Principal:
    user: User | None = None
    session: AuthSession | None = None
    token: ApiToken | None = None

    @property
    def roles(self) -> set[str]:
        if self.user is None:
            return {ROLE_ANONYMOUS}
        return {ROLE_ANONYMOUS, ROLE_AUTHENTICATED, *self.user.role_names}

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles


def _invalid_token() -> ApiError:
    return ApiError(
        401,
        "invalid_token",
        "Invalid or expired API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _parse_authorization(header: str) -> tuple[str, str | None]:
    """Return (token, username) from a Bearer or Basic authorization header."""
    scheme, _, credentials = header.partition(" ")
    scheme = scheme.lower()
    credentials = credentials.strip()
    if scheme == "bearer" and credentials:
        return credentials, None
    if scheme == "basic" and credentials:
        try:
            decoded = base64.b64decode(credentials, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            raise _invalid_token() from None
        username, sep, token = decoded.partition(":")
        if sep and token:
            # Only API tokens are accepted as the Basic password, never account passwords.
            return token, normalize_login(username)
    raise _invalid_token()


async def _authenticate_token(db: DbSession, header: str) -> Principal:
    token, username = _parse_authorization(header)
    api_token = await db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_secret(token)))
    now = datetime.now(UTC)
    if api_token is None or (api_token.expires_at is not None and api_token.expires_at <= now):
        raise _invalid_token()
    user = await db.get(User, api_token.user_id)
    if user is None or not user.is_active or (username is not None and username != user.username):
        raise _invalid_token()
    if api_token.last_used_at is None or now - api_token.last_used_at > ACTIVITY_UPDATE_INTERVAL:
        api_token.last_used_at = now
        await db.commit()
    return Principal(user=user, token=api_token)


async def _authenticate_session(db: DbSession, request: Request, session_id: str) -> Principal:
    session = await db.get(AuthSession, hash_secret(session_id))
    now = datetime.now(UTC)
    if (
        session is None
        or session.expires_at <= now
        or session.last_seen_at + SESSION_IDLE_TIMEOUT <= now
    ):
        return Principal()
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        return Principal()
    if request.method not in SAFE_METHODS:
        csrf = request.headers.get(CSRF_HEADER, "")
        if not secrets_equal(csrf, session.csrf_token):
            raise ApiError(403, "csrf_failed", "Missing or invalid CSRF token")
    if now - session.last_seen_at > ACTIVITY_UPDATE_INTERVAL:
        session.last_seen_at = now
        await db.commit()
    return Principal(user=user, session=session)


async def get_principal(request: Request, db: DbSession) -> Principal:
    authorization = request.headers.get("authorization")
    if authorization:
        return await _authenticate_token(db, authorization)
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        return await _authenticate_session(db, request, session_id)
    return Principal()


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def require_authenticated(principal: CurrentPrincipal) -> Principal:
    """Signed-in user; allowed even while a password change is pending."""
    if principal.user is None:
        raise ApiError(
            401,
            "not_authenticated",
            "Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


async def require_user(
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Principal:
    assert principal.user is not None
    if principal.user.must_change_password:
        raise ApiError(403, "password_change_required", "Password change required")
    return principal


async def require_admin(principal: Annotated[Principal, Depends(require_user)]) -> Principal:
    if not principal.is_admin:
        raise ApiError(403, "forbidden", "Administrator role required")
    return principal


AuthenticatedPrincipal = Annotated[Principal, Depends(require_authenticated)]
UserPrincipal = Annotated[Principal, Depends(require_user)]
AdminPrincipal = Annotated[Principal, Depends(require_admin)]
