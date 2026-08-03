"""The path the product is: seed, publish, subscribe, connect.

Every layer's unit tests can pass while the product does not work, because the failures that
matter here are seams — a store root the gateway reads but the API writes elsewhere, a pin the
catalog honours and the composer ignores. Only a test that spans the seam finds those.

The seeder runs as a subprocess, exactly as `python scripts/dev.py seed` runs it, and the tokens
it prints are the tokens the test authenticates with. A demo whose printed keys do not work is a
broken demo, and this is the only place that would notice.

Not collected by `dev.py test`: `testpaths` is `packages`. Run it with `python scripts/dev.py e2e`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response, Timeout
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl

from conftest import ROOT, skill_archive

_INCIDENT = "incident-response"
_PAYMENTS = "pci-payment-review"
_PLATFORM = "platform-team"
_CHECKOUT = "checkout-squad"

_TEAM_LINE = re.compile(r"^ {2}\S.*\((?P<slug>[a-z0-9-]+)\)$")
_KEY_LINE = re.compile(r"^ {4}API key\s+(?P<token>ashub_\S+)$")


def _parse_tokens(report: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    slug: str | None = None
    for line in report.splitlines():
        team = _TEAM_LINE.match(line)
        if team:
            slug = team.group("slug")
            continue
        key = _KEY_LINE.match(line)
        if key and slug:
            tokens[slug] = key.group("token")
    return tokens


@dataclass(frozen=True)
class Demo:
    api: AsyncClient
    tokens: dict[str, str]
    report: str
    connect: Callable[[str], Any]

    def headers(self, slug: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[slug]}"}


@pytest_asyncio.fixture
async def demo(tmp_path: Path) -> AsyncIterator[Demo]:
    from agentskills_hub_api.app import create_app
    from agentskills_hub_api.settings import Settings
    from agentskills_hub_gateway import GatewaySettings, create_gateway_app

    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'hub.db').as_posix()}"
    store_root = tmp_path / "store"

    seeded = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed.py"),
            "--database-url",
            database_url,
            "--store-root",
            str(store_root),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    tokens = _parse_tokens(seeded.stdout)

    gateway_app = create_gateway_app(
        GatewaySettings(
            database_url=database_url,
            store_root=str(store_root),
            allowed_hosts=("hub",),
            allowed_origins=(),
        )
    )
    gateway_transport = ASGITransport(app=gateway_app)

    def connect(slug: str) -> Any:
        credential = {"Authorization": f"Bearer {tokens[slug]}"}

        def factory(
            headers: dict[str, str] | None = None,
            timeout: Timeout | None = None,
            auth: Any = None,
        ) -> AsyncClient:
            return AsyncClient(
                transport=gateway_transport,
                headers={**(headers or {}), **credential},
                timeout=timeout,
                auth=auth,
            )

        return _session(f"http://hub/mcp/{slug}", factory)

    settings = Settings(database_url=database_url, store_root=str(store_root))
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://hub"
    ) as api:
        yield Demo(api=api, tokens=tokens, report=seeded.stdout, connect=connect)

    await gateway_app.state.gateway.dispose()


@asynccontextmanager
async def _session(url: str, factory: Any) -> AsyncIterator[ClientSession]:
    async with (
        streamablehttp_client(url, httpx_client_factory=factory) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def _catalog(session: ClientSession) -> str:
    result = await session.read_resource(AnyUrl("skills://catalog/markdown"))
    return str(result.contents[0].text)  # type: ignore[union-attr]


async def _body(session: ClientSession, skill_id: str) -> str:
    result = await session.call_tool("get_skill_body", {"skill_id": skill_id})
    return str(result.content[0].text)  # type: ignore[union-attr]


async def _publish(
    demo: Demo, slug: str, skill_id: str, version: str, description: str
) -> Response:
    return await demo.api.post(
        "/api/skills",
        headers=demo.headers(slug),
        data={"skill_id": skill_id, "version": version},
        files={
            "archive": (
                "skill.tar.gz",
                skill_archive(skill_id, description=description),
                "application/gzip",
            )
        },
    )


async def test_the_seeded_demo_is_ready_to_connect(demo: Demo) -> None:
    """What the manifest says, an agent finds — and nothing beyond it."""
    assert set(demo.tokens) == {_CHECKOUT, _PLATFORM}

    async with demo.connect(_CHECKOUT) as session:
        tools = {tool.name for tool in (await session.list_tools()).tools}
        assert {"get_skill_metadata", "get_skill_body", "list_skill_resources"} <= tools

        catalog = await _catalog(session)
        assert _INCIDENT in catalog
        # Published to the same Hub, owned by this very team, and still absent: publishing is
        # not subscribing, and the endpoint serves the subscription rather than the catalog.
        assert _PAYMENTS not in catalog

        assert "When to Declare an Incident" in await _body(session, _INCIDENT)

        # Resources travel with the skill, or progressive disclosure has nothing to disclose.
        resources = await session.call_tool("list_skill_resources", {"skill_id": _INCIDENT})
        assert "severity-levels.md" in str(resources.content[0].text)
        reference = await session.call_tool(
            "get_skill_reference", {"skill_id": _INCIDENT, "name": "severity-levels.md"}
        )
        assert "SEV1" in str(reference.content[0].text)

    async with demo.connect(_PLATFORM) as session:
        assert _INCIDENT not in await _catalog(session)


async def test_a_new_version_does_not_move_a_pinned_team_until_it_repins(demo: Demo) -> None:
    published = await _publish(demo, _PLATFORM, _INCIDENT, "1.1.0", "the second edition")
    assert published.status_code == 201, published.text

    async with demo.connect(_CHECKOUT) as session:
        assert "the second edition" not in await _catalog(session)

    repinned = await demo.api.patch(
        f"/api/teams/{_CHECKOUT}/subscriptions/{_INCIDENT}",
        headers=demo.headers(_CHECKOUT),
        json={"version": "1.1.0"},
    )
    assert repinned.status_code == 200, repinned.text

    async with demo.connect(_CHECKOUT) as session:
        assert "the second edition" in await _catalog(session)


async def test_a_skill_reaches_an_agent_only_once_its_team_subscribes(demo: Demo) -> None:
    async with demo.connect(_PLATFORM) as session:
        assert await _catalog(session) is not None

    subscribed = await demo.api.post(
        f"/api/teams/{_PLATFORM}/subscriptions",
        headers=demo.headers(_PLATFORM),
        json={"skill_id": _PAYMENTS, "version": "1.0.0"},
    )
    assert subscribed.status_code == 201, subscribed.text

    async with demo.connect(_PLATFORM) as session:
        assert _PAYMENTS in await _catalog(session)
        assert "cardholder data" in (await _body(session, _PAYMENTS)).lower()

    unsubscribed = await demo.api.delete(
        f"/api/teams/{_PLATFORM}/subscriptions/{_PAYMENTS}", headers=demo.headers(_PLATFORM)
    )
    assert unsubscribed.status_code == 204

    async with demo.connect(_PLATFORM) as session:
        assert _PAYMENTS not in await _catalog(session)


async def test_the_printed_endpoint_is_the_one_that_answers(demo: Demo) -> None:
    """The demo instructions are part of the demo: a wrong URL in the report is a broken run."""
    assert f"/mcp/{_CHECKOUT}" in demo.report
    async with demo.connect(_CHECKOUT) as session:
        assert (await session.list_tools()).tools
