"""The composed app answers for all three surfaces, and only for the ones it should.

Mounting is where a working API and a working gateway can still add up to a broken deployment, so
these tests are about paths and lifespan rather than about anything either edge already proves.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentskills_hub_api.settings import Settings
from agentskills_hub_core.database import create_engine, create_session_factory, session_scope
from agentskills_hub_core.repositories import ApiKeyRepository, TeamRepository
from agentskills_hub_gateway import GatewaySettings
from agentskills_hub_server import create_server_app
from conftest import Credential, upgrade_to_head

pytestmark = pytest.mark.asyncio

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "composed-app-test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@dataclass(frozen=True)
class ServerFixture:
    client: AsyncClient
    team: Credential
    web_root: Path


def _build(database_url: str, tmp_path: Path, web_root: Path | None) -> object:
    store_root = tmp_path / "store"
    return create_server_app(
        Settings(database_url=database_url, store_root=str(store_root)),
        GatewaySettings(
            database_url=database_url,
            store_root=str(store_root),
            allowed_hosts=("hub",),
            allowed_origins=(),
        ),
        web_root=str(web_root) if web_root else str(tmp_path / "absent"),
    )


@pytest_asyncio.fixture
async def server(database_url: str, tmp_path: Path) -> AsyncIterator[ServerFixture]:
    await asyncio.to_thread(upgrade_to_head, database_url)

    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        team, environment = await TeamRepository(session).create("checkout-squad", "Checkout")
        _, token = await ApiKeyRepository(session).issue(team.id, environment.id)
    await engine.dispose()

    web_root = tmp_path / "web"
    (web_root / "assets").mkdir(parents=True)
    (web_root / "index.html").write_text("<!doctype html><title>Hub</title>", encoding="utf-8")
    (web_root / "assets" / "app.js").write_text("export const hub = true;\n", encoding="utf-8")

    app = _build(database_url, tmp_path, web_root)
    # ASGITransport does not run lifespan, and the lifespan is the whole reason the composed app
    # needs a test: it is what disposes the mounted gateway.
    async with (
        app.router.lifespan_context(app),  # type: ignore[attr-defined]
        AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://hub",
        ) as client,
    ):
        yield ServerFixture(client, Credential("checkout-squad", token), web_root)


async def test_the_api_answers_from_the_composed_app(server: ServerFixture) -> None:
    response = await server.client.get("/api/health")

    assert response.status_code == 200


async def test_the_gateway_answers_from_the_composed_app(server: ServerFixture) -> None:
    response = await server.client.get(
        f"/mcp/{server.team.slug}/check", headers=server.team.headers
    )

    assert response.status_code == 200
    assert response.json()["team"] == server.team.slug


async def test_an_mcp_session_starts_through_the_mount(server: ServerFixture) -> None:
    """The prefix Starlette strips is restored, or every MCP request is a 404."""
    response = await server.client.post(
        f"/mcp/{server.team.slug}",
        headers={**MCP_HEADERS, **server.team.headers},
        content=json.dumps(INITIALIZE),
    )

    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"]


async def test_the_gateway_still_refuses_another_teams_endpoint(server: ServerFixture) -> None:
    response = await server.client.get("/mcp/platform-team/check", headers=server.team.headers)

    assert response.status_code == 403


async def test_the_ui_is_served_at_the_root(server: ServerFixture) -> None:
    response = await server.client.get("/")

    assert response.status_code == 200
    assert "<title>Hub</title>" in response.text


async def test_a_client_side_route_survives_a_reload(server: ServerFixture) -> None:
    response = await server.client.get("/skills/incident-response")

    assert response.status_code == 200
    assert "<title>Hub</title>" in response.text


async def test_an_unknown_api_path_is_a_404_and_not_the_ui(server: ServerFixture) -> None:
    """Otherwise a typo in a client returns 200 and a parse error instead of a 404."""
    response = await server.client.get("/api/skills/not-a-route/nope")

    assert response.status_code == 404
    assert "<title>Hub</title>" not in response.text


async def test_the_hub_runs_without_a_built_ui(database_url: str, tmp_path: Path) -> None:
    """The API and the gateway are the product; the UI is optional and its absence is not fatal."""
    await asyncio.to_thread(upgrade_to_head, database_url)
    app = _build(database_url, tmp_path, None)

    async with (
        app.router.lifespan_context(app),  # type: ignore[attr-defined]
        AsyncClient(
            transport=ASGITransport(app=app),  # type: ignore[arg-type]
            base_url="http://hub",
        ) as client,
    ):
        assert (await client.get("/api/health")).status_code == 200
        assert (await client.get("/")).status_code == 404
