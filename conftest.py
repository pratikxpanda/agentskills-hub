"""Fixtures shared by every package's tests.

A single root conftest rather than one per package: two files named `conftest.py` under `packages`
are two modules named `conftest`, which mypy refuses.

Every test runs against a schema built by Alembic, not by `SQLModel.metadata.create_all`. If the
migration and the models disagree, the tests fail rather than passing against a schema no
deployment will ever have.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_api.app import create_app
from agentskills_hub_api.settings import Settings
from agentskills_hub_core.database import create_engine, create_session_factory, session_scope
from agentskills_hub_core.repositories import ApiKeyRepository, TeamRepository

ROOT = Path(__file__).resolve().parent
_SCRIPT_LOCATION = "packages/core/agentskills-hub-core/agentskills_hub_core/migrations"


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / _SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade_to_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'hub.db'}"


@pytest.fixture
def make_alembic_config() -> Callable[[str], Config]:
    # A fixture rather than an import: with --import-mode=importlib there is no importable module
    # path to reach this file by.
    return alembic_config


@pytest.fixture
def migrate() -> Callable[[str], None]:
    return upgrade_to_head


@pytest_asyncio.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    # env.py drives an async engine through asyncio.run, so migrations run off the event loop.
    await asyncio.to_thread(upgrade_to_head, database_url)
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        yield session
    await engine.dispose()


def skill_markdown(
    name: str,
    description: str = "Guides an on-call engineer through triage, mitigation, and handover.",
    body: str = "## Triage\n\nStart with the alert.\n",
) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


@dataclass(frozen=True)
class Credential:
    slug: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True)
class ApiFixture:
    client: AsyncClient
    store_root: Path
    alice: Credential
    bob: Credential


ApiFactory = Callable[..., Awaitable[ApiFixture]]

_TEAMS = (("checkout-squad", "Checkout Squad"), ("platform-team", "Platform"))


@pytest_asyncio.fixture
async def api_factory(database_url: str, tmp_path: Path) -> AsyncIterator[ApiFactory]:
    """Build an app with two teams and a live credential each.

    A factory rather than a plain fixture because the archive-limit tests need to construct the
    app with different limits, and the limits are read once at construction.
    """
    async with AsyncExitStack() as stack:

        async def build(**overrides: Any) -> ApiFixture:
            await asyncio.to_thread(upgrade_to_head, database_url)
            store_root = tmp_path / "store"

            engine = create_engine(database_url)
            factory = create_session_factory(engine)
            credentials: list[Credential] = []
            async with session_scope(factory) as session:
                for slug, name in _TEAMS:
                    team, environment = await TeamRepository(session).create(slug, name)
                    _, token = await ApiKeyRepository(session).issue(team.id, environment.id)
                    credentials.append(Credential(slug, token))
            await engine.dispose()

            settings = Settings(database_url=database_url, store_root=str(store_root), **overrides)
            client = await stack.enter_async_context(
                AsyncClient(
                    transport=ASGITransport(app=create_app(settings)), base_url="http://hub"
                )
            )
            return ApiFixture(client, store_root, credentials[0], credentials[1])

        yield build


@pytest_asyncio.fixture
async def api(api_factory: ApiFactory) -> ApiFixture:
    return await api_factory()
