"""Background jobs, schedules, LDAP settings and LDAP fields of users

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ldap_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("host", sa.String(length=256), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("verify_certificate", sa.Boolean(), nullable=False),
        sa.Column("ca_certificate", sa.Text(), nullable=True),
        sa.Column("bind_dn", sa.String(length=1024), nullable=False),
        sa.Column("bind_password_encrypted", sa.Text(), nullable=True),
        sa.Column("user_base_dn", sa.String(length=1024), nullable=False),
        sa.Column("user_filter", sa.Text(), nullable=True),
        sa.Column("attr_username", sa.String(length=64), nullable=False),
        sa.Column("attr_first_name", sa.String(length=64), nullable=False),
        sa.Column("attr_last_name", sa.String(length=64), nullable=False),
        sa.Column("attr_display_name", sa.String(length=64), nullable=False),
        sa.Column("attr_email", sa.String(length=64), nullable=False),
        sa.Column("sync_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("sync_max_block_ratio", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('ldap', 'starttls', 'ldaps')", name=op.f("ck_ldap_settings_mode")
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_ldap_settings_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ldap_settings")),
    )
    op.create_table(
        "schedules",
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("job_type", name=op.f("pk_schedules")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("resource_key", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("progress_done", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_jobs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_jobs_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_status_scheduled_at", "jobs", ["status", "scheduled_at"], unique=False)
    op.create_index(op.f("ix_jobs_type"), "jobs", ["type"], unique=False)
    op.create_index(
        "uq_jobs_active_resource_key",
        "jobs",
        ["resource_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "ldap_group_mappings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("group_dn", sa.String(length=1024), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_ldap_group_mappings_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ldap_group_mappings")),
        sa.UniqueConstraint("group_dn", "role_id", name="uq_ldap_group_mappings"),
    )
    op.create_table(
        "job_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_logs_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_logs")),
    )
    op.create_index(op.f("ix_job_logs_job_id"), "job_logs", ["job_id"], unique=False)
    op.add_column("users", sa.Column("ldap_dn", sa.String(length=1024), nullable=True))
    op.add_column("users", sa.Column("ldap_object_guid", sa.String(length=36), nullable=True))
    op.add_column("users", sa.Column("ldap_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(op.f("uq_users_ldap_object_guid"), "users", ["ldap_object_guid"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_users_ldap_object_guid"), "users", type_="unique")
    op.drop_column("users", "ldap_synced_at")
    op.drop_column("users", "ldap_object_guid")
    op.drop_column("users", "ldap_dn")
    op.drop_index(op.f("ix_job_logs_job_id"), table_name="job_logs")
    op.drop_table("job_logs")
    op.drop_table("ldap_group_mappings")
    op.drop_index(
        "uq_jobs_active_resource_key",
        table_name="jobs",
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.drop_index(op.f("ix_jobs_type"), table_name="jobs")
    op.drop_index("ix_jobs_status_scheduled_at", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("schedules")
    op.drop_table("ldap_settings")
