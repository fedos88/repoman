"""Scheduled synchronization of domain users with AD (job `ldap_sync`, design §9.3)."""

from typing import Any

from sqlalchemy import select

from repoman.auth.sessions import delete_user_sessions
from repoman.db.models import User
from repoman.jobs.runner import JobContext, JobFailed
from repoman.ldap.directory import DirectoryUser, LdapError
from repoman.ldap.service import (
    LdapService,
    apply_directory_user,
    get_settings,
    mapped_role_ids,
    roles_for,
)
from repoman.users.service import count_active_admins

JOB_TYPE = "ldap_sync"
# The mass-block protection applies only from this number of users to block.
MASS_BLOCK_MIN_USERS = 3


async def ldap_sync(ctx: JobContext) -> dict[str, Any]:
    service: LdapService = ctx.services["ldap"]
    async with ctx.sessionmaker() as db:
        settings = await get_settings(db)
        if not settings.enabled:
            await ctx.log("LDAP is disabled, nothing to do")
            return {"skipped": True}
        max_block_ratio = settings.sync_max_block_ratio
        try:
            directory = service.factory(service.config(settings))
            role_map = await mapped_role_ids(db, service, directory)
        except LdapError as exc:
            raise JobFailed(f"{exc.code}: {exc.message}") from None

        users = list(
            await db.scalars(select(User).where(User.auth_source == "ldap").order_by(User.id))
        )
        await ctx.progress(0, len(users))

        # Phase 1: read the directory without changing anything.
        found: dict[int, DirectoryUser | None] = {}
        for index, user in enumerate(users, start=1):
            await ctx.check_cancelled()
            try:
                if user.ldap_object_guid:
                    dir_user = await service.call(directory.find_by_guid, user.ldap_object_guid)
                else:
                    dir_user = await service.call(directory.find_user, user.username)
            except LdapError as exc:
                raise JobFailed(f"{exc.code}: {exc.message}") from None
            found[user.id] = dir_user
            if index % 20 == 0:
                await ctx.progress(index)

        to_block = [
            u for u in users if u.is_active and (found[u.id] is None or found[u.id].disabled)
        ]
        if len(to_block) >= MASS_BLOCK_MIN_USERS and len(to_block) / len(users) > max_block_ratio:
            raise JobFailed(
                f"Mass-block protection: {len(to_block)} of {len(users)} users would be "
                f"blocked (limit {max_block_ratio:.0%}). Check the user base DN and filter; "
                "no changes were made."
            )

        # Phase 2: apply.
        stats = {"checked": len(users), "updated": 0, "blocked": 0, "unblocked": 0}
        for user in users:
            dir_user = found[user.id]
            if dir_user is None or dir_user.disabled:
                if not user.is_active:
                    continue
                if "admin" in user.role_names and await count_active_admins(db, user.id) == 0:
                    await ctx.log(f"Not blocking {user.username}: last administrator", "warning")
                    continue
                reason = "not found in directory" if dir_user is None else "disabled in AD"
                user.is_active = False
                user.blocked_by = "ldap_sync"
                await delete_user_sessions(db, user.id)
                stats["blocked"] += 1
                await ctx.log(f"Blocked {user.username}: {reason}", "warning")
                continue
            if not user.is_active and user.blocked_by == "ldap_sync":
                user.is_active = True
                user.blocked_by = None
                stats["unblocked"] += 1
                await ctx.log(f"Unblocked {user.username}")
            if await apply_directory_user(db, user, dir_user, roles_for(dir_user, role_map)):
                stats["updated"] += 1
        await db.commit()

    await ctx.progress(len(users), len(users))
    await ctx.log(
        "Checked {checked}, updated {updated}, blocked {blocked}, unblocked {unblocked}".format(
            **stats
        )
    )
    return stats
