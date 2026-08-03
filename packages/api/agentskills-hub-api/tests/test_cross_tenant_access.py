"""Cross-tenant access control.

A dedicated module, because this is the single control standing between one team and another
team's instruction set in v0.1.
"""

from __future__ import annotations

import logging

import pytest

from agentskills_hub_core.database import create_engine, create_session_factory, session_scope
from agentskills_hub_core.repositories import ApiKeyRepository
from agentskills_hub_core.security import mint_api_key
from conftest import ApiFactory, ApiFixture


async def test_health_needs_no_credential(api: ApiFixture) -> None:
    response = await api.client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_a_valid_credential_resolves_to_its_own_team(api: ApiFixture) -> None:
    response = await api.client.get(f"/api/teams/{api.alice.slug}", headers=api.alice.headers)

    assert response.status_code == 200
    assert response.json()["slug"] == api.alice.slug


async def test_team_a_cannot_read_team_b(api: ApiFixture) -> None:
    response = await api.client.get(f"/api/teams/{api.bob.slug}", headers=api.alice.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "team_mismatch"


async def test_the_catalog_is_shared_but_its_subscription_state_is_not(api: ApiFixture) -> None:
    """The catalog is the one endpoint where reading another team's rows is the point.

    Skills are org-scoped in v0.1, so hiding them would defeat the product. What must not cross
    the boundary is `is_subscribed` and `subscribed_version`, which are answers about the caller.
    tests/test_catalog.py asserts they do not; this records that the exposure is deliberate.
    """
    response = await api.client.get("/api/skills", headers=api.alice.headers)

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_the_path_segment_never_selects_the_team(api: ApiFixture) -> None:
    """A forged segment must not become the answer, even when it names a real team."""
    forged = await api.client.get(f"/api/teams/{api.bob.slug}", headers=api.alice.headers)
    honest = await api.client.get(f"/api/teams/{api.alice.slug}", headers=api.alice.headers)

    assert forged.status_code == 403
    assert honest.json()["slug"] == api.alice.slug


async def test_a_missing_credential_is_rejected(api: ApiFixture) -> None:
    response = await api.client.get(f"/api/teams/{api.alice.slug}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "ashub_only_two", "ashub__", "Bearer ashub_a_b", mint_api_key().token],
)
async def test_unknown_credentials_are_rejected_without_detail(api: ApiFixture, token: str) -> None:
    response = await api.client.get(
        f"/api/teams/{api.alice.slug}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["details"] == []
    # An unknown prefix and a wrong secret must not be distinguishable from the response.
    assert body["error"]["message"] == "Authentication failed."


async def test_a_tampered_secret_is_rejected(api: ApiFixture) -> None:
    scheme, prefix, secret = api.alice.token.split("_")
    tampered = f"{scheme}_{prefix}_{'0' * len(secret)}"

    response = await api.client.get(
        f"/api/teams/{api.alice.slug}", headers={"Authorization": f"Bearer {tampered}"}
    )

    assert response.status_code == 401


async def test_a_revoked_credential_fails_closed(api: ApiFixture, database_url: str) -> None:
    _, prefix, _ = api.alice.token.split("_")

    engine = create_engine(database_url)
    async with session_scope(create_session_factory(engine)) as session:
        keys = ApiKeyRepository(session)
        key = await keys.get_by_prefix(prefix)
        assert key is not None
        await keys.revoke(key.id)
    await engine.dispose()

    response = await api.client.get(f"/api/teams/{api.alice.slug}", headers=api.alice.headers)
    assert response.status_code == 401


async def test_repeated_failures_are_rate_limited(api_factory: ApiFactory) -> None:
    api = await api_factory(auth_failure_limit=3)
    headers = {"Authorization": "Bearer ashub_deadbeef_cafe"}

    statuses = [
        (await api.client.get("/api/teams/anyone", headers=headers)).status_code for _ in range(5)
    ]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]


async def test_tokens_never_reach_the_logs(
    api: ApiFixture, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await api.client.get(f"/api/teams/{api.alice.slug}", headers=api.alice.headers)
        await api.client.get(
            f"/api/teams/{api.alice.slug}",
            headers={"Authorization": f"Bearer {api.alice.token}x"},
        )

    _, _, secret = api.alice.token.split("_")
    assert api.alice.token not in caplog.text
    assert secret not in caplog.text
