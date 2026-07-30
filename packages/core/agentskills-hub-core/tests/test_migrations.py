"""Migrations must build the schema from empty and take it back to empty."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_TABLES = {
    "api_key",
    "environment",
    "skill",
    "skill_version",
    "subscription",
    "team",
}


def _table_names(url: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_async_engine(url)
        async with engine.connect() as connection:
            names = await connection.run_sync(
                lambda sync_conn: set(sa.inspect(sync_conn).get_table_names())
            )
        await engine.dispose()
        return names

    return asyncio.run(run())


def test_upgrade_creates_schema_from_empty(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'hub.db'}"
    command.upgrade(make_alembic_config(url), "head")
    assert _table_names(url) >= EXPECTED_TABLES


def test_downgrade_returns_to_empty(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'hub.db'}"
    config = make_alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    remaining = _table_names(url)
    assert not (EXPECTED_TABLES & remaining)


def test_upgrade_downgrade_upgrade_is_repeatable(
    tmp_path: Path, make_alembic_config: Callable[[str], Config]
) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'hub.db'}"
    config = make_alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert _table_names(url) >= EXPECTED_TABLES
