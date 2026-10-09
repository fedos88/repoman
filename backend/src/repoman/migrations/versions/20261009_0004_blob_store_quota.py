"""Soft quota of blob stores

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("blob_stores", sa.Column("quota_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("blob_stores", "quota_bytes")
