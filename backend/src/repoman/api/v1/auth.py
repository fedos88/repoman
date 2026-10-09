from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select

from repoman.api.v1.schemas import LoginIn, MeOut
from repoman.auth.dependencies import CurrentPrincipal
from repoman.auth.ratelimit import LoginRateLimiter
from repoman.auth.security import hash_password, password_needs_rehash, verify_password
from repoman.auth.sessions import (
    clear_session_cookies,
    client_ip,
    create_session,
    set_session_cookies,
)
from repoman.db.deps import DbSession
from repoman.db.models import AuthSession, User
from repoman.errors import ApiError
from repoman.ldap.service import ldap_sign_in
from repoman.users.names import normalize_login

router = APIRouter(prefix="/auth", tags=["auth"])


def _limiter(request: Request) -> LoginRateLimiter:
    return request.app.state.login_rate_limiter


@router.post("/login", response_model=MeOut)
async def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> MeOut:
    username = normalize_login(body.username)
    ip = client_ip(request)
    limiter = _limiter(request)
    if limiter.is_blocked(username, ip):
        raise ApiError(429, "too_many_attempts", "Too many failed sign-in attempts, try later")

    user = await db.scalar(select(User).where(User.username == username))
    authenticated: User | None = None
    if user is not None and user.auth_source == "local":
        if await verify_password(user.password_hash, body.password):
            authenticated = user
            if user.password_hash and password_needs_rehash(user.password_hash):
                user.password_hash = await hash_password(body.password)
    else:
        # A domain user, or an unknown name that may exist in AD (created on first sign-in).
        authenticated = await ldap_sign_in(
            db, request.app.state.ldap, user, username, body.password
        )
        if authenticated is None and user is None:
            await verify_password(None, body.password)  # same timing as for a local user
    if authenticated is None:
        limiter.record_failure(username, ip)
        raise ApiError(401, "invalid_credentials", "Invalid username or password")
    user = authenticated
    if not user.is_active:
        await db.commit()  # keep the profile refreshed from AD
        raise ApiError(403, "user_blocked", "User is blocked")

    limiter.reset(username, ip)
    user.last_login_at = datetime.now(UTC)
    session_id, session = await create_session(db, user, request)
    await db.commit()

    set_session_cookies(response, request, session_id, session)
    return MeOut.of_user(user)


@router.post("/logout", status_code=204)
async def logout(principal: CurrentPrincipal, response: Response, db: DbSession) -> Response:
    if principal.session is not None:
        await db.execute(
            delete(AuthSession).where(AuthSession.id_hash == principal.session.id_hash)
        )
        await db.commit()
    clear_session_cookies(response)
    response.status_code = 204
    return response
