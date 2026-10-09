"""Blob stores and blobs (storage model with blob ids)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blob_stores",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('filesystem', 's3')", name=op.f("ck_blob_stores_type")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blob_stores")),
        sa.UniqueConstraint("name", name=op.f("uq_blob_stores_name")),
    )
    op.create_table(
        "blobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blob_store_id", sa.BigInteger(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["blob_store_id"], ["blob_stores.id"], name=op.f("fk_blobs_blob_store_id_blob_stores")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blobs")),
    )
    op.create_index(op.f("ix_blobs_blob_store_id"), "blobs", ["blob_store_id"], unique=False)
    op.create_index(
        "ix_blobs_deleted_at",
        "blobs",
        ["deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_blobs_deleted_at",
        table_name="blobs",
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.drop_index(op.f("ix_blobs_blob_store_id"), table_name="blobs")
    op.drop_table("blobs")
    op.drop_table("blob_stores")
