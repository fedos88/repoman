from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import delete, select

from repoman.api.v1.schemas import (
    ChangeOwnPasswordIn,
    MeOut,
    TokenCreatedOut,
    TokenCreateIn,
    TokenOut,
)
from repoman.auth.dependencies import AuthenticatedPrincipal, UserPrincipal
from repoman.auth.security import hash_secret, new_api_token, token_display_prefix, verify_password
from repoman.db.deps import DbSession
from repoman.db.models import ApiToken
from repoman.errors import ApiError
from repoman.users.service import require_local, set_password

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def get_me(principal: AuthenticatedPrincipal) -> MeOut:
    assert principal.user is not None
    return MeOut.of_user(principal.user)


@router.put("/password", status_code=204)
async def change_own_password(
    body: ChangeOwnPasswordIn, principal: AuthenticatedPrincipal, db: DbSession
) -> Response:
    user = principal.user
    assert user is not None
    require_local(user, "ldap_user_password", "Password of a domain user is managed in AD")
    if not await verify_password(user.password_hash, body.current_password):
        raise ApiError(422, "invalid_current_password", "Current password is incorrect")
    # Other sessions are signed out; the current one stays.
    await set_password(
        db,
        user,
        body.new_password,
        must_change=False,
        keep_session_id_hash=principal.session.id_hash if principal.session else None,
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/tokens", response_model=list[TokenOut])
async def list_own_tokens(principal: UserPrincipal, db: DbSession) -> list[TokenOut]:
    assert principal.user is not None
    tokens = await db.scalars(
        select(ApiToken).where(ApiToken.user_id == principal.user.id).order_by(ApiToken.id)
    )
    return [TokenOut.of(token) for token in tokens]


@router.post("/tokens", response_model=TokenCreatedOut, status_code=201)
async def create_own_token(
    body: TokenCreateIn, principal: UserPrincipal, db: DbSession
) -> TokenCreatedOut:
    assert principal.user is not None
    secret = new_api_token()
    token = ApiToken(
        user_id=principal.user.id,
        name=body.name,
        prefix=token_display_prefix(secret),
        token_hash=hash_secret(secret),
        expires_at=(
            datetime.now(UTC) + timedelta(days=body.expires_in_days)
            if body.expires_in_days is not None
            else None
        ),
    )
    db.add(token)
    await db.commit()
    return TokenCreatedOut(**TokenOut.of(token).model_dump(), token=secret)


@router.delete("/tokens/{token_id}", status_code=204)
async def delete_own_token(token_id: int, principal: UserPrincipal, db: DbSession) -> Response:
    assert principal.user is not None
    result = await db.execute(
        delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == principal.user.id)
    )
    if result.rowcount == 0:
        raise ApiError(404, "token_not_found", "Token not found")
    await db.commit()
    return Response(status_code=204)
