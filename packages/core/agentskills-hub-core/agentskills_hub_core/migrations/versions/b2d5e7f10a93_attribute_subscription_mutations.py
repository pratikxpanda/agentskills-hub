"""attribute subscription mutations

Revision ID: b2d5e7f10a93
Revises: 7a1f2c9d4e60
Create Date: 2026-08-03 14:41:52.906311
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

import agentskills_hub_core.types

revision: str = "b2d5e7f10a93"
down_revision: str | None = "7a1f2c9d4e60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("subscription") as batch:
        batch.add_column(
            sa.Column("created_by", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True)
        )
        batch.add_column(
            sa.Column("updated_at", agentskills_hub_core.types.UtcDateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column("updated_by", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("subscription") as batch:
        batch.drop_column("updated_by")
        batch.drop_column("updated_at")
        batch.drop_column("created_by")
