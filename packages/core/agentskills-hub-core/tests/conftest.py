"""Shared fixtures.

Every test runs against a schema built by Alembic, not by `SQLModel.metadata.create_all`. If the
migration and the models disagree, the tests fail rather than passing against a schema no
deployment will ever have.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_core.database import create_engine, create_session_factory

ROOT = Path(__file__).resolve().parents[4]
_SCRIPT_LOCATION = "packages/core/agentskills-hub-core/agentskills_hub_core/migrations"


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / _SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _upgrade(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'hub.db'}"


@pytest.fixture
def make_alembic_config() -> Callable[[str], Config]:
    # A fixture rather than a cross-package import: with --import-mode=importlib there is no
    # importable `tests` package to import a helper from.
    return alembic_config


@pytest_asyncio.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    # env.py drives an async engine through asyncio.run, so migrations run off the event loop.
    await asyncio.to_thread(_upgrade, database_url)
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()
