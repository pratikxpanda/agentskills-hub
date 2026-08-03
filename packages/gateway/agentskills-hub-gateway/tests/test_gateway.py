"""The per-team MCP endpoint.

Driven by the real MCP client rather than by raw HTTP. The endpoint's contract is not "returns
JSON"; it is "an agent can connect to this and find its team's skills", and only a client that
speaks the protocol can assert that.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl

from conftest import Credential, GatewayFixture, skill_archive

_INCIDENT = "incident-response"
_PAYMENTS = "pci-payment-review"


async def _publish(
    client: AsyncClient,
    credential: Credential,
    skill_id: str,
    version: str = "1.0.0",
    description: str | None = None,
) -> Response:
    archive = skill_archive(skill_id, description=description)
    return await client.post(
        "/api/skills",
        headers=credential.headers,
        data={"skill_id": skill_id, "version": version},
        files={"archive": ("skill.tar.gz", archive, "application/gzip")},
    )


async def _subscribe(
    client: AsyncClient, credential: Credential, skill_id: str, version: str = "1.0.0"
) -> Response:
    return await client.post(
        f"/api/teams/{credential.slug}/subscriptions",
        headers=credential.headers,
        json={"skill_id": skill_id, "version": version},
    )


@asynccontextmanager
async def _connect(gateway: GatewayFixture, credential: Credential) -> AsyncIterator[ClientSession]:
    async with (
        streamablehttp_client(
            gateway.url(credential), httpx_client_factory=gateway.client_factory(credential)
        ) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def _skill_ids(session: ClientSession) -> list[str]:
    result = await session.read_resource(AnyUrl("skills://catalog/markdown"))
    catalog = result.contents[0].text  # type: ignore[union-attr]
    return sorted({line for line in (_INCIDENT, _PAYMENTS) if line in catalog})


@pytest_asyncio.fixture
async def subscribed(gateway: GatewayFixture) -> GatewayFixture:
    client = gateway.api.client
    await _publish(client, gateway.api.alice, _INCIDENT)
    await _publish(client, gateway.api.bob, _PAYMENTS)
    await _subscribe(client, gateway.api.bob, _INCIDENT)
    await _subscribe(client, gateway.api.bob, _PAYMENTS)
    await _subscribe(client, gateway.api.alice, _INCIDENT)
    return gateway


async def test_a_client_is_served_its_own_teams_pinned_skills(subscribed: GatewayFixture) -> None:
    async with _connect(subscribed, subscribed.api.bob) as session:
        tools = await session.list_tools()
        assert "get_skill_body" in {tool.name for tool in tools.tools}
        assert await _skill_ids(session) == [_INCIDENT, _PAYMENTS]

        body = await session.call_tool("get_skill_body", {"skill_id": _INCIDENT})
        assert "Start with the alert." in body.content[0].text  # type: ignore[union-attr]

    async with _connect(subscribed, subscribed.api.alice) as session:
        # Alice publishes both but subscribes to one. Publishing is not subscribing.
        assert await _skill_ids(session) == [_INCIDENT]


async def _metadata(session: ClientSession, skill_id: str) -> str:
    result = await session.call_tool("get_skill_metadata", {"skill_id": skill_id})
    return str(result.content[0].text)  # type: ignore[union-attr]


async def test_the_version_served_is_the_pinned_one_not_the_latest(
    subscribed: GatewayFixture,
) -> None:
    """Publishing a newer version must not change what a pinned subscriber is served."""
    await _publish(
        subscribed.api.client,
        subscribed.api.alice,
        _INCIDENT,
        version="2.0.0",
        description="the second edition",
    )

    async with _connect(subscribed, subscribed.api.bob) as session:
        assert "the second edition" not in await _metadata(session, _INCIDENT)

    response = await subscribed.check(subscribed.api.bob)
    assert response.json()["skill_count"] == 2


async def test_a_team_with_no_subscriptions_gets_a_valid_empty_session(
    gateway: GatewayFixture,
) -> None:
    """An empty catalog is an answer. A 404 would be read as broken wiring."""
    async with _connect(gateway, gateway.api.alice) as session:
        assert await _skill_ids(session) == []
        assert (await session.list_tools()).tools != []


async def test_unsubscribing_removes_the_skill_from_the_next_connection(
    subscribed: GatewayFixture,
) -> None:
    await subscribed.api.client.delete(
        f"/api/teams/{subscribed.api.bob.slug}/subscriptions/{_INCIDENT}",
        headers=subscribed.api.bob.headers,
    )

    async with _connect(subscribed, subscribed.api.bob) as session:
        assert await _skill_ids(session) == [_PAYMENTS]


async def test_repinning_changes_what_is_served(subscribed: GatewayFixture) -> None:
    await _publish(
        subscribed.api.client,
        subscribed.api.alice,
        _INCIDENT,
        version="2.0.0",
        description="the second edition",
    )
    await subscribed.api.client.patch(
        f"/api/teams/{subscribed.api.bob.slug}/subscriptions/{_INCIDENT}",
        headers=subscribed.api.bob.headers,
        json={"version": "2.0.0"},
    )

    async with _connect(subscribed, subscribed.api.bob) as session:
        assert "the second edition" in await _metadata(session, _INCIDENT)

    assert (await subscribed.check(subscribed.api.bob)).json()["unavailable"] == []


async def test_two_teams_connected_at_once_share_no_registry(subscribed: GatewayFixture) -> None:
    async def skills_for(credential: Credential) -> list[str]:
        async with _connect(subscribed, credential) as session:
            await asyncio.sleep(0)
            return await _skill_ids(session)

    bob, alice = await asyncio.gather(
        skills_for(subscribed.api.bob), skills_for(subscribed.api.alice)
    )

    assert bob == [_INCIDENT, _PAYMENTS]
    assert alice == [_INCIDENT]


async def test_a_skill_missing_from_the_store_costs_that_skill_not_the_session(
    subscribed: GatewayFixture,
) -> None:
    """One unreadable skill must not be able to take a team's whole session down with it."""
    import shutil

    shutil.rmtree(subscribed.api.store_root / "skills" / _INCIDENT)

    async with _connect(subscribed, subscribed.api.bob) as session:
        assert await _skill_ids(session) == [_PAYMENTS]

    body = (await subscribed.check(subscribed.api.bob)).json()
    assert body["skills"] == [_PAYMENTS]
    assert body["unavailable"] == [f"{_INCIDENT}@1.0.0"]


async def test_the_check_endpoint_reports_the_composition(subscribed: GatewayFixture) -> None:
    response = await subscribed.check(subscribed.api.bob)

    assert response.status_code == 200
    assert response.json() == {
        "team": subscribed.api.bob.slug,
        "skill_count": 2,
        "skills": [_INCIDENT, _PAYMENTS],
        "unavailable": [],
    }


async def test_a_connection_for_another_teams_slug_is_refused(subscribed: GatewayFixture) -> None:
    response = await subscribed.check(subscribed.api.bob, slug=subscribed.api.alice.slug)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "team_mismatch"


async def test_an_unauthenticated_connection_is_refused(subscribed: GatewayFixture) -> None:
    anonymous = Credential(subscribed.api.bob.slug, "")
    response = await subscribed.check(anonymous)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("slug_of", ["self", "other"])
async def test_refusals_happen_before_a_registry_is_built(
    subscribed: GatewayFixture, monkeypatch: pytest.MonkeyPatch, slug_of: str
) -> None:
    """Composition reads the store. An unauthenticated caller must not be able to cause that."""
    from agentskills_hub_gateway import app as gateway_app

    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("a registry was composed for a refused request")

    monkeypatch.setattr(gateway_app, "compose", explode)

    credential = (
        Credential(subscribed.api.bob.slug, "")
        if slug_of == "self"
        else Credential(subscribed.api.alice.slug, subscribed.api.bob.token)
    )
    response = await subscribed.check(credential, slug=credential.slug)

    assert response.status_code in (401, 403)


async def test_repeated_authentication_failures_are_throttled(gateway: GatewayFixture) -> None:
    wrong = Credential(gateway.api.bob.slug, "ashub_deadbeefcafe_" + "0" * 64)

    codes = [(await gateway.check(wrong)).status_code for _ in range(12)]

    assert codes[0] == 401
    assert codes[-1] == 429


async def test_an_unconfigured_host_is_refused_by_the_transport(gateway: GatewayFixture) -> None:
    """The allowlist is configuration, so it needs a test that fails when it stops being applied.

    Left at the SDK's default, the transport answers 421 to every hostname that is not loopback,
    which is a failure mode worth discovering here rather than in a deployment.
    """
    credential = gateway.api.bob
    async with AsyncClient(
        transport=gateway.transport, base_url="http://rebound.example.com"
    ) as client:
        response = await client.post(
            f"/mcp/{credential.slug}",
            headers={
                **credential.headers,
                "content-type": "application/json",
                "accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )

    assert response.status_code == 421
