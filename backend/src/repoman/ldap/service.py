"""LDAP integration: settings, sign-in of domain users, role mapping (design §9)."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repoman.crypto import SecretBox, SecretDecryptionError
from repoman.db.models import ROLE_ADMIN, LdapGroupMapping, LdapSettings, Role, User, UserRole
from repoman.errors import ApiError
from repoman.ldap.directory import Directory, DirectoryUser, Ldap3Directory, LdapConfig, LdapError
from repoman.users.service import count_active_admins, username_exists

logger = logging.getLogger(__name__)

T = TypeVar("T")
DirectoryFactory = Callable[[LdapConfig], Directory]


class LdapService:
    def __init__(self, secret_box: SecretBox, factory: DirectoryFactory = Ldap3Directory) -> None:
        self.secret_box = secret_box
        self.factory = factory

    @staticmethod
    async def call(fn: Callable[..., T], *args: Any) -> T:
        """Run a blocking directory call in a thread."""
        return await asyncio.to_thread(fn, *args)

    def config(self, settings: LdapSettings, bind_password: str | None = None) -> LdapConfig:
        if bind_password is None:
            if not settings.bind_password_encrypted:
                bind_password = ""
            else:
                try:
                    bind_password = self.secret_box.decrypt(settings.bind_password_encrypted)
                except SecretDecryptionError as exc:
                    raise LdapError("ldap_secret_unreadable", str(exc)) from None
        return LdapConfig(
            mode=settings.mode,
            host=settings.host,
            port=settings.port,
            verify_certificate=settings.verify_certificate,
            ca_certificate=settings.ca_certificate,
            bind_dn=settings.bind_dn,
            bind_password=bind_password,
            user_base_dn=settings.user_base_dn,
            user_filter=settings.user_filter,
            attr_username=settings.attr_username,
            attr_first_name=settings.attr_first_name,
            attr_last_name=settings.attr_last_name,
            attr_display_name=settings.attr_display_name,
            attr_email=settings.attr_email,
        )

    async def directory(self, db: AsyncSession) -> Directory | None:
        """Directory for the saved settings, or None when LDAP is disabled."""
        settings = await get_settings(db)
        if not settings.enabled:
            return None
        return self.factory(self.config(settings))


def default_settings() -> LdapSettings:
    return LdapSettings(
        id=1,
        enabled=False,
        mode="ldaps",
        host="",
        port=636,
        verify_certificate=True,
        bind_dn="",
        user_base_dn="",
        attr_username="sAMAccountName",
        attr_first_name="givenName",
        attr_last_name="sn",
        attr_display_name="displayName",
        attr_email="mail",
        sync_interval_seconds=3600,
        sync_max_block_ratio=0.5,
    )


async def get_settings(db: AsyncSession) -> LdapSettings:
    """Saved settings, or defaults (not added to the session) if never saved."""
    return await db.get(LdapSettings, 1) or default_settings()


def ldap_unavailable(exc: LdapError) -> ApiError:
    return ApiError(503, "ldap_unavailable", f"LDAP is unavailable: {exc.message}")


# --- roles -------------------------------------------------------------------------------


async def mapped_role_ids(
    db: AsyncSession, service: LdapService, directory: Directory
) -> dict[str, set[int]]:
    """Group SID -> role ids of the configured mappings."""
    mappings = list(await db.scalars(select(LdapGroupMapping)))
    if not mappings:
        return {}
    sids = await service.call(directory.group_sids, sorted({m.group_dn for m in mappings}))
    result: dict[str, set[int]] = {}
    for mapping in mappings:
        sid = sids.get(mapping.group_dn)
        if sid is None:
            logger.warning("LDAP group mapping: group not found: %s", mapping.group_dn)
            continue
        result.setdefault(sid, set()).add(mapping.role_id)
    return result


def roles_for(dir_user: DirectoryUser, role_map: dict[str, set[int]]) -> set[int]:
    return {role_id for sid in dir_user.group_sids for role_id in role_map.get(sid, ())}


async def apply_directory_user(
    db: AsyncSession, user: User, dir_user: DirectoryUser, role_ids: set[int]
) -> bool:
    """Update profile and LDAP roles of a domain user. Returns True if anything changed."""
    changed = False
    values = {
        "first_name": dir_user.first_name,
        "last_name": dir_user.last_name,
        "display_name": dir_user.display_name,
        "email": dir_user.email,
        "ldap_dn": dir_user.dn,
        "ldap_object_guid": dir_user.guid,
    }
    if dir_user.username and dir_user.username != user.username:
        # Renamed in AD: follow the new name unless it is taken by another account.
        if not await username_exists(db, dir_user.username):
            values["username"] = dir_user.username
    for name, value in values.items():
        if getattr(user, name) != value:
            setattr(user, name, value)
            changed = True
    user.ldap_synced_at = datetime.now(UTC)

    current = {ur.role_id for ur in user.roles if ur.source == "ldap"}
    if current != role_ids:
        removed = current - role_ids
        admin_role_ids = {ur.role_id for ur in user.roles if ur.role.name == ROLE_ADMIN}
        if removed & admin_role_ids and user.is_active:
            has_other_admin_source = any(
                ur.role.name == ROLE_ADMIN and ur.source != "ldap" for ur in user.roles
            )
            if not has_other_admin_source and await count_active_admins(db, user.id) == 0:
                # Never leave the system without an administrator.
                logger.warning("LDAP: keeping admin role of %s (last administrator)", user.username)
                role_ids = role_ids | (removed & admin_role_ids)
        if current != role_ids:
            user.roles = [ur for ur in user.roles if ur.source != "ldap" or ur.role_id in role_ids]
            for role_id in sorted(role_ids - current):
                role = await db.get(Role, role_id)
                if role is not None:
                    user.roles.append(UserRole(role=role, source="ldap"))
            changed = True
    return changed


# --- sign-in -----------------------------------------------------------------------------


async def ldap_sign_in(
    db: AsyncSession, service: LdapService, user: User | None, username: str, password: str
) -> User | None:
    """Authenticate a domain user; creates the RepoMan user on first sign-in.

    Returns None for invalid credentials. Raises ApiError 503 if LDAP is unavailable.
    """
    directory = await service.directory(db)
    if directory is None:
        return None
    try:
        dir_user = await service.call(directory.authenticate, username, password)
        if dir_user is None:
            return None
        role_ids = roles_for(dir_user, await mapped_role_ids(db, service, directory))
    except LdapError as exc:
        raise ldap_unavailable(exc) from None

    if user is None:
        user = await db.scalar(select(User).where(User.ldap_object_guid == dir_user.guid))
    if user is None:
        user = User(
            username=dir_user.username or username,
            auth_source="ldap",
            must_change_password=False,
            is_active=True,
            roles=[],
        )
        db.add(user)
    elif user.auth_source != "ldap":
        return None
    if not user.is_active and user.blocked_by == "ldap_sync":
        # The account is valid in AD again; sign-in re-checks the directory.
        user.is_active = True
        user.blocked_by = None
    await apply_directory_user(db, user, dir_user, role_ids)
    await db.flush()  # a new user gets its id (needed for the session)
    return user


async def ensure_not_in_directory(db: AsyncSession, service: LdapService, username: str) -> None:
    """A local user must not shadow a domain account while LDAP is enabled."""
    directory = await service.directory(db)
    if directory is None:
        return
    try:
        found = await service.call(directory.find_user, username)
    except LdapError as exc:
        raise ldap_unavailable(exc) from None
    if found is not None:
        raise ApiError(409, "username_exists_in_ldap", "A domain user with this name exists")
