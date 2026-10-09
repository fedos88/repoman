"""Users, built-in roles, sessions and API tokens

Revision ID: 0001
Revises:
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("username", sa.String(256), nullable=False),
        sa.Column("auth_source", sa.String(16), nullable=False),
        sa.Column("password_hash", sa.String(256)),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("first_name", sa.String(256)),
        sa.Column("last_name", sa.String(256)),
        sa.Column("display_name", sa.String(256)),
        sa.Column("email", sa.String(320)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("blocked_by", sa.String(16)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("auth_source IN ('local', 'ldap')", name="ck_users_auth_source"),
        sa.CheckConstraint(
            "blocked_by IS NULL OR blocked_by IN ('admin', 'ldap_sync')",
            name="ck_users_blocked_by",
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    roles = op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(1024)),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.bulk_insert(
        roles,
        [
            {"name": "admin", "builtin": True, "description": "Full access"},
            {"name": "authenticated", "builtin": True, "description": "Any signed-in user"},
            {"name": "anonymous", "builtin": True, "description": "Any request"},
        ],
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_roles_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.BigInteger(),
            sa.ForeignKey("roles.id", ondelete="CASCADE", name="fk_user_roles_role_id_roles"),
            primary_key=True,
        ),
        sa.Column("source", sa.String(16), primary_key=True),
        sa.CheckConstraint("source IN ('manual', 'ldap')", name="ck_user_roles_source"),
    )

    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_api_tokens_user_id_users"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
    )
    op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("api_tokens")
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
