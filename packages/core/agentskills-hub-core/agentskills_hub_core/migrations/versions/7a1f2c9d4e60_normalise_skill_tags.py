"""normalise skill tags

Revision ID: 7a1f2c9d4e60
Revises: 3e668c4b0094
Create Date: 2026-08-03 10:12:04.118273
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "7a1f2c9d4e60"
down_revision: str | None = "3e668c4b0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_skill_tag = sa.table(
    "skill_tag",
    sa.column("id", sa.Uuid()),
    sa.column("skill_id", sa.Uuid()),
    sa.column("tag", sa.String()),
)


def upgrade() -> None:
    op.create_table(
        "skill_tag",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skill.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "tag", name="uq_skill_tag"),
    )
    op.create_index(op.f("ix_skill_tag_skill_id"), "skill_tag", ["skill_id"])
    op.create_index(op.f("ix_skill_tag_tag"), "skill_tag", ["tag"])

    _copy_tags(from_json=True)
    with op.batch_alter_table("skill") as batch:
        batch.drop_column("tags")


def downgrade() -> None:
    with op.batch_alter_table("skill") as batch:
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))

    _copy_tags(from_json=False)
    op.drop_index(op.f("ix_skill_tag_tag"), table_name="skill_tag")
    op.drop_index(op.f("ix_skill_tag_skill_id"), table_name="skill_tag")
    op.drop_table("skill_tag")


def _copy_tags(*, from_json: bool) -> None:
    """Move tags between the JSON column and the table, in whichever direction is being applied.

    Decoding in Python rather than in SQL: the column is portable `JSON`, and every dialect spells
    array iteration differently.
    """
    connection = op.get_bind()
    if from_json:
        rows = connection.execute(sa.text("SELECT id, tags FROM skill")).fetchall()
        values = [
            {"id": uuid.uuid4(), "skill_id": skill_id, "tag": tag}
            for skill_id, raw in rows
            for tag in sorted(set(json.loads(raw or "[]")))
        ]
        if values:
            op.bulk_insert(_skill_tag, values)
        return

    rows = connection.execute(
        sa.text("SELECT skill_id, tag FROM skill_tag ORDER BY skill_id, tag")
    ).fetchall()
    grouped: dict[uuid.UUID, list[str]] = {}
    for skill_id, tag in rows:
        grouped.setdefault(skill_id, []).append(tag)
    for skill_id, tags in grouped.items():
        connection.execute(
            sa.text("UPDATE skill SET tags = :tags WHERE id = :id"),
            {"tags": json.dumps(tags), "id": skill_id},
        )
