"""Cross-tenant access control.

The spec asks for a dedicated module here, because this is the single control standing between one
team and another team's instruction set in v0.1.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from agentskills_hub_api.app import create_app
from agentskills_hub_api.settings import Settings
from agentskills_hub_core.database import create_engine, create_session_factory, session_scope
from agentskills_hub_core.repositories import ApiKeyRepository, TeamRepository
from agentskills_hub_core.security import mint_api_key


class Credential:
    def __init__(self, slug: str, token: str) -> None:
        self.slug = slug
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest_asyncio.fixture
async def api(
    database_url: str, tmp_path_factory: pytest.TempPathFactory, migrate: Callable[[str], None]
) -> AsyncIterator[tuple[AsyncClient, Credential, Credential]]:
    import asyncio

    await asyncio.to_thread(migrate, database_url)
    store_root = tmp_path_factory.mktemp("store")

    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    credentials: list[Credential] = []
    async with session_scope(factory) as session:
        for slug, name in (("checkout-squad", "Checkout Squad"), ("platform-team", "Platform")):
            team, environment = await TeamRepository(session).create(slug, name)
            _, token = await ApiKeyRepository(session).issue(team.id, environment.id)
            credentials.append(Credential(slug, token))
    await engine.dispose()

    settings = Settings(database_url=database_url, store_root=str(store_root))
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://hub") as client:
        yield client, credentials[0], credentials[1]


async def test_health_needs_no_credential(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    client, _, _ = api
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_a_valid_credential_resolves_to_its_own_team(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    client, alice, _ = api
    response = await client.get(f"/api/teams/{alice.slug}", headers=alice.headers)

    assert response.status_code == 200
    assert response.json()["slug"] == alice.slug


async def test_team_a_cannot_read_team_b(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    client, alice, bob = api
    response = await client.get(f"/api/teams/{bob.slug}", headers=alice.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "team_mismatch"


async def test_the_path_segment_never_selects_the_team(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    """A forged segment must not become the answer, even when it names a real team."""
    client, alice, bob = api
    forged = await client.get(f"/api/teams/{bob.slug}", headers=alice.headers)
    honest = await client.get(f"/api/teams/{alice.slug}", headers=alice.headers)

    assert forged.status_code == 403
    assert honest.json()["slug"] == alice.slug


async def test_a_missing_credential_is_rejected(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    client, alice, _ = api
    response = await client.get(f"/api/teams/{alice.slug}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "ashub_only_two", "ashub__", "Bearer ashub_a_b", mint_api_key().token],
)
async def test_unknown_credentials_are_rejected_without_detail(
    api: tuple[AsyncClient, Credential, Credential], token: str
) -> None:
    client, alice, _ = api
    response = await client.get(
        f"/api/teams/{alice.slug}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["details"] == []
    # An unknown prefix and a wrong secret must not be distinguishable from the response.
    assert body["error"]["message"] == "Authentication failed."


async def test_a_tampered_secret_is_rejected(
    api: tuple[AsyncClient, Credential, Credential],
) -> None:
    client, alice, _ = api
    scheme, prefix, secret = alice.token.split("_")
    tampered = f"{scheme}_{prefix}_{'0' * len(secret)}"

    response = await client.get(
        f"/api/teams/{alice.slug}", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401


async def test_a_revoked_credential_fails_closed(
    api: tuple[AsyncClient, Credential, Credential], database_url: str
) -> None:
    client, alice, _ = api
    _, prefix, _ = alice.token.split("_")

    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        keys = ApiKeyRepository(session)
        key = await keys.get_by_prefix(prefix)
        assert key is not None
        await keys.revoke(key.id)
    await engine.dispose()

    response = await client.get(f"/api/teams/{alice.slug}", headers=alice.headers)
    assert response.status_code == 401


async def test_repeated_failures_are_rate_limited(
    database_url: str, tmp_path_factory: pytest.TempPathFactory, migrate: Callable[[str], None]
) -> None:
    import asyncio

    await asyncio.to_thread(migrate, database_url)
    settings = Settings(
        database_url=database_url,
        store_root=str(tmp_path_factory.mktemp("store")),
        auth_failure_limit=3,
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hub") as client:
        headers = {"Authorization": "Bearer ashub_deadbeef_cafe"}
        statuses = [
            (await client.get("/api/teams/anyone", headers=headers)).status_code for _ in range(5)
        ]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]


async def test_tokens_never_reach_the_logs(
    api: tuple[AsyncClient, Credential, Credential], caplog: pytest.LogCaptureFixture
) -> None:
    client, alice, _ = api
    with caplog.at_level(logging.DEBUG):
        await client.get(f"/api/teams/{alice.slug}", headers=alice.headers)
        await client.get(
            f"/api/teams/{alice.slug}", headers={"Authorization": f"Bearer {alice.token}x"}
        )

    _, _, secret = alice.token.split("_")
    assert alice.token not in caplog.text
    assert secret not in caplog.text
