from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select

from repoman.api.v1.jobs import JobOut
from repoman.auth.dependencies import AdminPrincipal
from repoman.db.deps import DbSession
from repoman.db.models import IMPLICIT_ROLES, Job, LdapGroupMapping, LdapSettings, Role, Schedule
from repoman.errors import ApiError
from repoman.jobs.queue import enqueue
from repoman.jobs.schedules import upsert_schedule
from repoman.ldap.directory import LdapError
from repoman.ldap.service import LdapService, default_settings, get_settings, mapped_role_ids
from repoman.ldap.sync import JOB_TYPE as LDAP_SYNC_JOB
from repoman.users.names import normalize_login

router = APIRouter(prefix="/ldap", tags=["ldap"])

Dn = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1024)]
Attr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class LdapSettingsBase(BaseModel):
    enabled: bool = False
    mode: Literal["ldap", "starttls", "ldaps"] = "ldaps"
    host: Annotated[str, StringConstraints(strip_whitespace=True, max_length=256)] = ""
    port: Annotated[int, Field(ge=1, le=65535)] = 636
    verify_certificate: bool = True
    ca_certificate: str | None = None
    bind_dn: Dn = ""
    user_base_dn: Dn = ""
    user_filter: str | None = None
    attr_username: Attr = "sAMAccountName"
    attr_first_name: Attr = "givenName"
    attr_last_name: Attr = "sn"
    attr_display_name: Attr = "displayName"
    attr_email: Attr = "mail"
    sync_interval_seconds: Annotated[int, Field(ge=300, le=7 * 86400)] = 3600
    sync_max_block_ratio: Annotated[float, Field(gt=0, le=1)] = 0.5


class LdapSettingsIn(LdapSettingsBase):
    # Omitted or null: keep the saved password.
    bind_password: str | None = None

    @model_validator(mode="after")
    def _required_when_enabled(self) -> "LdapSettingsIn":
        if self.enabled:
            missing = [f for f in ("host", "bind_dn", "user_base_dn") if not getattr(self, f)]
            if missing:
                raise ValueError(f"Required when LDAP is enabled: {', '.join(missing)}")
        return self


class LdapSettingsOut(LdapSettingsBase):
    has_bind_password: bool
    updated_at: datetime | None


class LdapTestIn(LdapSettingsIn):
    test_username: str | None = None


class LdapTestUser(BaseModel):
    dn: str
    username: str
    display_name: str | None
    email: str | None
    disabled: bool
    roles: list[str]


class LdapTestOut(BaseModel):
    ok: bool
    error_code: str | None = None
    message: str | None = None
    user_found: bool | None = None
    user: LdapTestUser | None = None


class GroupMappingIn(BaseModel):
    group_dn: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1024)
    ]
    role: str


class GroupMappingOut(BaseModel):
    id: int
    group_dn: str
    role: str


class SyncStatusOut(BaseModel):
    enabled: bool
    interval_seconds: int | None
    next_run_at: datetime | None
    last_job: JobOut | None


def _service(request: Request) -> LdapService:
    return request.app.state.ldap


def _settings_out(settings: LdapSettings, saved: bool) -> LdapSettingsOut:
    fields = LdapSettingsBase.model_fields
    return LdapSettingsOut(
        **{name: getattr(settings, name) for name in fields},
        has_bind_password=bool(settings.bind_password_encrypted),
        updated_at=settings.updated_at if saved else None,
    )


def _apply(settings: LdapSettings, body: LdapSettingsBase) -> None:
    for name in LdapSettingsBase.model_fields:
        setattr(settings, name, getattr(body, name))
    settings.ca_certificate = (settings.ca_certificate or "").strip() or None
    settings.user_filter = (settings.user_filter or "").strip() or None


@router.get("/settings", response_model=LdapSettingsOut)
async def get_ldap_settings(_: AdminPrincipal, db: DbSession) -> LdapSettingsOut:
    saved = await db.get(LdapSettings, 1)
    return _settings_out(saved or default_settings(), saved is not None)


@router.put("/settings", response_model=LdapSettingsOut)
async def put_ldap_settings(
    body: LdapSettingsIn, request: Request, _: AdminPrincipal, db: DbSession
) -> LdapSettingsOut:
    settings = await db.get(LdapSettings, 1)
    if settings is None:
        settings = default_settings()
        db.add(settings)
    _apply(settings, body)
    if body.bind_password is not None:
        settings.bind_password_encrypted = (
            _service(request).secret_box.encrypt(body.bind_password) if body.bind_password else None
        )
    if settings.enabled and not settings.bind_password_encrypted:
        raise ApiError(422, "ldap_bind_password_required", "Bind password is required")
    await upsert_schedule(
        db, LDAP_SYNC_JOB, settings.sync_interval_seconds, enabled=settings.enabled
    )
    await db.commit()
    return _settings_out(settings, True)


@router.post("/test", response_model=LdapTestOut)
async def test_ldap(
    body: LdapTestIn, request: Request, _: AdminPrincipal, db: DbSession
) -> LdapTestOut:
    """Check the given (possibly unsaved) settings; the saved password is used if omitted."""
    service = _service(request)
    missing = [f for f in ("host", "bind_dn", "user_base_dn") if not getattr(body, f)]
    if missing:
        raise ApiError(
            422, "ldap_settings_incomplete", "Required settings are missing", {"fields": missing}
        )
    settings = default_settings()
    _apply(settings, body)
    saved = await get_settings(db)
    try:
        if body.bind_password:
            config = service.config(settings, bind_password=body.bind_password)
        else:
            settings.bind_password_encrypted = saved.bind_password_encrypted
            config = service.config(settings)
        directory = service.factory(config)
        await service.call(directory.check_connection)
        if not body.test_username:
            return LdapTestOut(ok=True)
        dir_user = await service.call(directory.find_user, normalize_login(body.test_username))
        if dir_user is None:
            return LdapTestOut(ok=True, user_found=False)
        role_map = await mapped_role_ids(db, service, directory)
    except LdapError as exc:
        return LdapTestOut(ok=False, error_code=exc.code, message=exc.message)
    role_ids = {rid for sid in dir_user.group_sids for rid in role_map.get(sid, ())}
    roles = sorted(r.name for r in await db.scalars(select(Role).where(Role.id.in_(role_ids))))
    return LdapTestOut(
        ok=True,
        user_found=True,
        user=LdapTestUser(
            dn=dir_user.dn,
            username=dir_user.username,
            display_name=dir_user.display_name,
            email=dir_user.email,
            disabled=dir_user.disabled,
            roles=roles,
        ),
    )


@router.get("/group-mappings", response_model=list[GroupMappingOut])
async def list_group_mappings(_: AdminPrincipal, db: DbSession) -> list[GroupMappingOut]:
    mappings = await db.scalars(select(LdapGroupMapping).order_by(LdapGroupMapping.id))
    return [GroupMappingOut(id=m.id, group_dn=m.group_dn, role=m.role.name) for m in mappings]


@router.post("/group-mappings", response_model=GroupMappingOut, status_code=201)
async def create_group_mapping(
    body: GroupMappingIn, _: AdminPrincipal, db: DbSession
) -> GroupMappingOut:
    if body.role in IMPLICIT_ROLES:
        raise ApiError(422, "role_not_assignable", "Role cannot be assigned explicitly")
    role = await db.scalar(select(Role).where(Role.name == body.role))
    if role is None:
        raise ApiError(422, "role_not_found", "Role not found")
    exists = await db.scalar(
        select(LdapGroupMapping).where(
            LdapGroupMapping.group_dn == body.group_dn, LdapGroupMapping.role_id == role.id
        )
    )
    if exists is not None:
        raise ApiError(409, "group_mapping_exists", "This mapping already exists")
    mapping = LdapGroupMapping(group_dn=body.group_dn, role=role)
    db.add(mapping)
    await db.commit()
    return GroupMappingOut(id=mapping.id, group_dn=mapping.group_dn, role=role.name)


@router.delete("/group-mappings/{mapping_id}", status_code=204)
async def delete_group_mapping(mapping_id: int, _: AdminPrincipal, db: DbSession) -> Response:
    mapping = await db.get(LdapGroupMapping, mapping_id)
    if mapping is None:
        raise ApiError(404, "group_mapping_not_found", "Group mapping not found")
    await db.delete(mapping)
    await db.commit()
    return Response(status_code=204)


@router.post("/sync", response_model=JobOut, status_code=202)
async def start_sync(request: Request, principal: AdminPrincipal, db: DbSession) -> JobOut:
    settings = await get_settings(db)
    if not settings.enabled:
        raise ApiError(409, "ldap_disabled", "LDAP is disabled")
    job = await enqueue(
        db,
        LDAP_SYNC_JOB,
        resource_key=LDAP_SYNC_JOB,
        created_by_id=principal.user.id if principal.user else None,
    )
    await db.commit()
    request.app.state.job_runner.wake()
    return JobOut.of(job)


@router.get("/sync/status", response_model=SyncStatusOut)
async def sync_status(_: AdminPrincipal, db: DbSession) -> SyncStatusOut:
    settings = await get_settings(db)
    schedule = await db.get(Schedule, LDAP_SYNC_JOB)
    job = await db.scalar(
        select(Job).where(Job.type == LDAP_SYNC_JOB).order_by(Job.id.desc()).limit(1)
    )
    return SyncStatusOut(
        enabled=settings.enabled,
        interval_seconds=schedule.interval_seconds if schedule else None,
        next_run_at=schedule.next_run_at if schedule and schedule.enabled else None,
        last_job=JobOut.of(job) if job else None,
    )
