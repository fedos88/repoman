"""Ensure there is an active administrator (first start and break-glass recovery)."""

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from repoman.auth.security import hash_password
from repoman.config import Settings
from repoman.db.models import ROLE_ADMIN, User, UserRole
from repoman.users.service import count_active_admins, get_role

logger = logging.getLogger(__name__)


async def ensure_admin(sessionmaker: async_sessionmaker, settings: Settings) -> None:
    async with sessionmaker() as db:
        if await count_active_admins(db) > 0:
            return

        username = settings.admin_user
        generated = settings.admin_password is None
        password = (
            secrets.token_urlsafe(16)
            if settings.admin_password is None
            else settings.admin_password.get_secret_value()
        )

        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, auth_source="local", roles=[])
            db.add(user)
        elif user.auth_source != "local":
            raise RuntimeError(
                f"No active administrator, and REPOMAN_ADMIN_USER '{username}' is not a local "
                "user. Set REPOMAN_ADMIN_USER to a different name."
            )
        user.password_hash = await hash_password(password)
        user.must_change_password = generated
        user.is_active = True
        user.blocked_by = None

        admin_role = await get_role(db, ROLE_ADMIN)
        assert admin_role is not None, "built-in role is created by migrations"
        if not any(ur.role_id == admin_role.id and ur.source == "manual" for ur in user.roles):
            user.roles.append(UserRole(role=admin_role, source="manual"))
        await db.commit()

    if generated:
        # Shown once: the password must be changed at first sign-in.
        logger.warning(
            "No active administrator found. Created administrator '%s' with generated "
            "password: %s (it must be changed at first sign-in)",
            username,
            password,
        )
    else:
        logger.warning(
            "No active administrator found. Administrator '%s' is set up with the password "
            "from REPOMAN_ADMIN_PASSWORD",
            username,
        )
