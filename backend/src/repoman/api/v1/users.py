from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import delete, func, or_, select

from repoman.api.v1.schemas import (
    ResetPasswordIn,
    RolesIn,
    TokenOut,
    UserCreateIn,
    UserOut,
    UserPage,
    UserUpdateIn,
)
from repoman.auth.dependencies import AdminPrincipal
from repoman.auth.security import hash_password
from repoman.db.deps import DbSession
from repoman.db.models import ApiToken, User
from repoman.errors import ApiError
from repoman.ldap.service import ensure_not_in_directory
from repoman.users.service import (
    block_user,
    ensure_not_last_admin,
    get_user_or_404,
    require_local,
    set_manual_roles,
    set_password,
    unblock_user,
    username_exists,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserPage)
async def list_users(
    _: AdminPrincipal,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserPage:
    condition = None
    if q and q.strip():
        needle = q.strip().lower()
        condition = or_(
            *(
                func.lower(column).contains(needle, autoescape=True)
                for column in (User.username, User.display_name, User.email)
            )
        )
    total_query = select(func.count(User.id))
    items_query = select(User).order_by(User.username).limit(limit).offset(offset)
    if condition is not None:
        total_query = total_query.where(condition)
        items_query = items_query.where(condition)
    total = int(await db.scalar(total_query) or 0)
    users = await db.scalars(items_query)
    return UserPage(items=[UserOut.of(user) for user in users], total=total)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateIn, request: Request, _: AdminPrincipal, db: DbSession
) -> UserOut:
    if await username_exists(db, body.username):
        raise ApiError(409, "username_taken", "Username is already taken")
    await ensure_not_in_directory(db, request.app.state.ldap, body.username)
    user = User(
        username=body.username,
        auth_source="local",
        password_hash=await hash_password(body.password),
        must_change_password=body.must_change_password,
        first_name=body.first_name,
        last_name=body.last_name,
        display_name=body.display_name,
        email=body.email,
        is_active=True,
        roles=[],
    )
    db.add(user)
    await set_manual_roles(db, user, body.roles)
    await db.commit()
    return UserOut.of(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, _: AdminPrincipal, db: DbSession) -> UserOut:
    return UserOut.of(await get_user_or_404(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdateIn, _: AdminPrincipal, db: DbSession
) -> UserOut:
    user = await get_user_or_404(db, user_id)
    require_local(user, "ldap_user_readonly", "Profile of a domain user is managed in AD")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    return UserOut.of(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, principal: AdminPrincipal, db: DbSession) -> Response:
    user = await get_user_or_404(db, user_id)
    require_local(user, "ldap_user_cannot_be_deleted", "Domain users can only be blocked")
    if principal.user is not None and principal.user.id == user.id:
        raise ApiError(409, "cannot_delete_self", "You cannot delete yourself")
    await ensure_not_last_admin(db, user)
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)


@router.post("/{user_id}/block", response_model=UserOut)
async def block(user_id: int, principal: AdminPrincipal, db: DbSession) -> UserOut:
    user = await get_user_or_404(db, user_id)
    if principal.user is not None and principal.user.id == user.id:
        raise ApiError(409, "cannot_block_self", "You cannot block yourself")
    await block_user(db, user, "admin")
    await db.commit()
    return UserOut.of(user)


@router.post("/{user_id}/unblock", response_model=UserOut)
async def unblock(user_id: int, _: AdminPrincipal, db: DbSession) -> UserOut:
    user = await get_user_or_404(db, user_id)
    unblock_user(user)
    await db.commit()
    return UserOut.of(user)


@router.put("/{user_id}/password", status_code=204)
async def reset_password(
    user_id: int, body: ResetPasswordIn, principal: AdminPrincipal, db: DbSession
) -> Response:
    user = await get_user_or_404(db, user_id)
    require_local(user, "ldap_user_password", "Password of a domain user is managed in AD")
    is_self = principal.user is not None and principal.user.id == user.id
    await set_password(
        db,
        user,
        body.password,
        must_change=body.must_change_password,
        keep_session_id_hash=principal.session.id_hash if is_self and principal.session else None,
    )
    await db.commit()
    return Response(status_code=204)


@router.put("/{user_id}/roles", response_model=UserOut)
async def set_roles(user_id: int, body: RolesIn, _: AdminPrincipal, db: DbSession) -> UserOut:
    user = await get_user_or_404(db, user_id)
    await set_manual_roles(db, user, body.roles)
    await db.commit()
    return UserOut.of(user)


@router.get("/{user_id}/tokens", response_model=list[TokenOut])
async def list_user_tokens(user_id: int, _: AdminPrincipal, db: DbSession) -> list[TokenOut]:
    await get_user_or_404(db, user_id)
    tokens = await db.scalars(
        select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.id)
    )
    return [TokenOut.of(token) for token in tokens]


@router.delete("/{user_id}/tokens/{token_id}", status_code=204)
async def delete_user_token(
    user_id: int, token_id: int, _: AdminPrincipal, db: DbSession
) -> Response:
    result = await db.execute(
        delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user_id)
    )
    if result.rowcount == 0:
        raise ApiError(404, "token_not_found", "Token not found")
    await db.commit()
    return Response(status_code=204)
