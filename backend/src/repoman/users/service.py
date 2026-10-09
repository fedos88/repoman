"""User management rules shared by the API and startup bootstrap."""

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.auth.security import hash_password
from repoman.auth.sessions import delete_user_sessions
from repoman.db.models import IMPLICIT_ROLES, ROLE_ADMIN, Role, User, UserRole
from repoman.errors import ApiError


async def get_user_or_404(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "User not found")
    return user


async def get_role(db: AsyncSession, name: str) -> Role | None:
    return await db.scalar(select(Role).where(Role.name == name))


async def username_exists(db: AsyncSession, username: str) -> bool:
    return bool(await db.scalar(select(exists().where(User.username == username))))


async def count_active_admins(db: AsyncSession, exclude_user_id: int | None = None) -> int:
    """Count active administrators.

    Locks the admin role row so concurrent changes of administrators are serialized
    until the end of the transaction (protection of the last administrator).
    """
    await db.execute(select(Role.id).where(Role.name == ROLE_ADMIN).with_for_update())
    statement = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.name == ROLE_ADMIN, User.is_active.is_(True))
    )
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return int(await db.scalar(statement) or 0)


async def ensure_not_last_admin(db: AsyncSession, user: User) -> None:
    if ROLE_ADMIN in user.role_names and await count_active_admins(db, user.id) == 0:
        raise ApiError(409, "last_admin", "The last active administrator cannot be removed")


async def set_manual_roles(db: AsyncSession, user: User, role_names: list[str]) -> None:
    wanted = set(role_names)
    not_assignable = sorted(wanted & set(IMPLICIT_ROLES))
    if not_assignable:
        raise ApiError(
            422,
            "role_not_assignable",
            "Role cannot be assigned explicitly",
            {"roles": not_assignable},
        )
    roles = {
        role.name: role for role in await db.scalars(select(Role).where(Role.name.in_(wanted)))
    }
    unknown = sorted(wanted - roles.keys())
    if unknown:
        raise ApiError(422, "role_not_found", "Role not found", {"roles": unknown})

    current_manual = {ur.role.name for ur in user.roles if ur.source == "manual"}
    if ROLE_ADMIN in current_manual and ROLE_ADMIN not in wanted:
        has_admin_from_other_source = any(
            ur.role.name == ROLE_ADMIN and ur.source != "manual" for ur in user.roles
        )
        if not has_admin_from_other_source:
            await ensure_not_last_admin(db, user)

    user.roles = [ur for ur in user.roles if ur.source != "manual" or ur.role.name in wanted]
    for name in sorted(wanted - current_manual):
        user.roles.append(UserRole(role=roles[name], source="manual"))


async def block_user(db: AsyncSession, user: User, blocked_by: str) -> None:
    if user.is_active:
        await ensure_not_last_admin(db, user)
    user.is_active = False
    user.blocked_by = blocked_by
    await delete_user_sessions(db, user.id)


def unblock_user(user: User) -> None:
    user.is_active = True
    user.blocked_by = None


async def set_password(
    db: AsyncSession,
    user: User,
    password: str,
    *,
    must_change: bool,
    keep_session_id_hash: str | None = None,
) -> None:
    user.password_hash = await hash_password(password)
    user.must_change_password = must_change
    await delete_user_sessions(db, user.id, keep_id_hash=keep_session_id_hash)


def require_local(user: User, code: str, message: str) -> None:
    if user.auth_source != "local":
        raise ApiError(409, code, message)
