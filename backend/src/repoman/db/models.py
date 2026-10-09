import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from repoman.db.base import Base

AUTH_SOURCES = ("local", "ldap")
BLOCKED_BY = ("admin", "ldap_sync")
ROLE_SOURCES = ("manual", "ldap")

ROLE_ADMIN = "admin"
ROLE_AUTHENTICATED = "authenticated"
ROLE_ANONYMOUS = "anonymous"
BUILTIN_ROLES = (ROLE_ADMIN, ROLE_AUTHENTICATED, ROLE_ANONYMOUS)
# Implicit roles are derived from the request and are never assigned explicitly.
IMPLICIT_ROLES = (ROLE_AUTHENTICATED, ROLE_ANONYMOUS)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> datetime:
    return datetime.now(UTC)


# Timestamps are set on the Python side as well, so they are available after commit
# without an extra round trip (sessions use expire_on_commit=False).
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("auth_source", AUTH_SOURCES), name="auth_source"),
        CheckConstraint(
            f"blocked_by IS NULL OR {_in('blocked_by', BLOCKED_BY)}", name="blocked_by"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(256), unique=True)
    auth_source: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(256))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    first_name: Mapped[str | None] = mapped_column(String(256))
    last_name: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(320))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked_by: Mapped[str | None] = mapped_column(String(16))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), onupdate=_now
    )
    ldap_dn: Mapped[str | None] = mapped_column(String(1024))
    # objectGUID is stable across renames and moves in AD.
    ldap_object_guid: Mapped[str | None] = mapped_column(String(36), unique=True)
    ldap_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_names(self) -> list[str]:
        return sorted({user_role.role.name for user_role in self.roles})


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(1024))


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (CheckConstraint(_in("source", ROLE_SOURCES), name="source"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), primary_key=True)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(lazy="joined")


class AuthSession(TimestampMixin, Base):
    __tablename__ = "sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class ApiToken(TimestampMixin, Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Storage -----------------------------------------------------------------------------

BLOB_STORE_TYPES = ("filesystem", "s3")


class BlobStore(Base):
    __tablename__ = "blob_stores"
    __table_args__ = (CheckConstraint(_in("type", BLOB_STORE_TYPES), name="type"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class Blob(Base):
    """Immutable stored object (design §7.1); the database is the source of truth."""

    __tablename__ = "blobs"
    __table_args__ = (
        Index(
            "ix_blobs_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    blob_store_id: Mapped[int] = mapped_column(ForeignKey("blob_stores.id"), index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    # Set when no longer referenced; the object is removed after the grace period.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Background jobs ---------------------------------------------------------------------

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
JOB_ACTIVE_STATUSES = ("queued", "running")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        # At most one active job per resource (e.g. one LDAP sync, one purge of a repository).
        Index(
            "uq_jobs_active_resource_key",
            "resource_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_jobs_status_scheduled_at", "status", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    resource_key: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    level: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)


class Schedule(Base):
    __tablename__ = "schedules"

    job_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# --- LDAP / Active Directory -------------------------------------------------------------

LDAP_MODES = ("ldap", "starttls", "ldaps")


class LdapSettings(Base):
    """Singleton row (id = 1)."""

    __tablename__ = "ldap_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(_in("mode", LDAP_MODES), name="mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(16), default="ldaps")
    host: Mapped[str] = mapped_column(String(256), default="")
    port: Mapped[int] = mapped_column(Integer, default=636)
    verify_certificate: Mapped[bool] = mapped_column(Boolean, default=True)
    ca_certificate: Mapped[str | None] = mapped_column(Text)
    bind_dn: Mapped[str] = mapped_column(String(1024), default="")
    bind_password_encrypted: Mapped[str | None] = mapped_column(Text)
    user_base_dn: Mapped[str] = mapped_column(String(1024), default="")
    user_filter: Mapped[str | None] = mapped_column(Text)
    attr_username: Mapped[str] = mapped_column(String(64), default="sAMAccountName")
    attr_first_name: Mapped[str] = mapped_column(String(64), default="givenName")
    attr_last_name: Mapped[str] = mapped_column(String(64), default="sn")
    attr_display_name: Mapped[str] = mapped_column(String(64), default="displayName")
    attr_email: Mapped[str] = mapped_column(String(64), default="mail")
    sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    sync_max_block_ratio: Mapped[float] = mapped_column(Float, default=0.5)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), onupdate=_now
    )


class LdapGroupMapping(Base):
    __tablename__ = "ldap_group_mappings"
    __table_args__ = (UniqueConstraint("group_dn", "role_id", name="uq_ldap_group_mappings"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    group_dn: Mapped[str] = mapped_column(String(1024))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    role: Mapped[Role] = relationship(lazy="joined")
