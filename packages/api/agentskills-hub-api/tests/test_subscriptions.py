"""Subscriptions.

The interesting assertions here are the refusals. A subscription is the only thing that changes
what an agent sees, so the tests are written against the ways that could happen without anyone
deciding it: a floating pin, a version that was never published, another team's request, or an
upgrade that arrived because a publisher acted rather than a subscriber.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_core import (
    SkillLifecycle,
    SkillRepository,
    SubscriptionRepository,
    SubscriptionStatus,
    VersionStatus,
    Visibility,
    create_engine,
    create_session_factory,
    session_scope,
)
from conftest import ApiFixture, Credential, skill_archive

_INCIDENT = "incident-response"
_PAYMENTS = "pci-payment-review"


async def _publish(
    client: AsyncClient,
    credential: Credential,
    skill_id: str,
    *,
    version: str = "1.0.0",
    description: str | None = None,
) -> Response:
    return await client.post(
        "/api/skills",
        headers=credential.headers,
        data={"skill_id": skill_id, "version": version},
        files={
            "archive": ("skill.tar.gz", skill_archive(skill_id, description), "application/gzip")
        },
    )


@asynccontextmanager
async def _session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_engine(database_url)
    try:
        async with session_scope(create_session_factory(engine)) as session:
            yield session
    finally:
        await engine.dispose()


def _url(credential: Credential, suffix: str = "") -> str:
    return f"/api/teams/{credential.slug}/subscriptions{suffix}"


async def _subscribe(
    api: ApiFixture, credential: Credential, skill_id: str, version: str
) -> Response:
    return await api.client.post(
        _url(credential),
        headers=credential.headers,
        json={"skill_id": skill_id, "version": version},
    )


@pytest_asyncio.fixture
async def published(api: ApiFixture) -> ApiFixture:
    await _publish(
        api.client,
        api.alice,
        _INCIDENT,
        description="Guides an on-call engineer through triage and handover.",
    )
    await _publish(
        api.client,
        api.bob,
        _PAYMENTS,
        description="Reviews changes to payment code against PCI scope.",
    )
    return api


async def test_subscribing_pins_one_version_and_says_who_did_it(published: ApiFixture) -> None:
    response = await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    assert response.status_code == 201
    body = response.json()
    assert body["skill_id"] == _INCIDENT
    assert body["owner"] == published.alice.slug
    assert body["version"] == "1.0.0"
    assert body["latest_version"] == "1.0.0"
    assert body["update_available"] is False
    assert body["lifecycle"] == SkillLifecycle.ACTIVE.value
    assert body["origin"] == "manual"
    assert body["subscribed_at"] is not None
    # No users until v0.4, so the credential is the principal. The token is `scheme_prefix_secret`
    # and only the prefix is recorded, so the audit trail is not itself a secret.
    assert body["subscribed_by"] == published.bob.token.split("_")[1]
    assert body["subscribed_by"] not in published.bob.token.split("_")[2]
    assert body["updated_at"] is None
    assert body["updated_by"] is None


async def test_the_list_shows_only_the_calling_teams_pins(published: ApiFixture) -> None:
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    mine = await published.client.get(_url(published.bob), headers=published.bob.headers)
    theirs = await published.client.get(_url(published.alice), headers=published.alice.headers)

    assert [item["skill_id"] for item in mine.json()] == [_INCIDENT]
    assert theirs.json() == []


async def test_publishing_a_newer_version_flags_the_pin_without_moving_it(
    published: ApiFixture,
) -> None:
    """The whole argument for refusing `latest` rests on this pair of assertions."""
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")
    assert (
        await _publish(published.client, published.alice, _INCIDENT, version="1.1.0")
    ).status_code == 201

    response = await published.client.get(_url(published.bob), headers=published.bob.headers)

    entry = response.json()[0]
    assert entry["version"] == "1.0.0"
    assert entry["latest_version"] == "1.1.0"
    assert entry["update_available"] is True


async def test_an_older_published_version_is_not_an_upgrade(published: ApiFixture) -> None:
    await _publish(published.client, published.alice, _INCIDENT, version="1.10.0")
    await _subscribe(published, published.bob, _INCIDENT, "1.10.0")

    entry = (await published.client.get(_url(published.bob), headers=published.bob.headers)).json()[
        0
    ]

    # Lexicographically `1.9.0` beats `1.10.0`; by semver precedence it does not.
    await _publish(published.client, published.alice, _INCIDENT, version="1.9.0")
    assert entry["update_available"] is False
    refreshed = (
        await published.client.get(_url(published.bob), headers=published.bob.headers)
    ).json()[0]
    assert refreshed["latest_version"] == "1.10.0"
    assert refreshed["update_available"] is False


@pytest.mark.parametrize("version", ["latest", "1.x", "^1.0.0", "1.0", ">=1.0.0"])
async def test_a_floating_pin_is_not_a_version(published: ApiFixture, version: str) -> None:
    response = await _subscribe(published, published.bob, _INCIDENT, version)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_identifier"


async def test_subscribing_twice_is_a_conflict_not_a_silent_repin(published: ApiFixture) -> None:
    await _publish(published.client, published.alice, _INCIDENT, version="2.0.0")
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    response = await _subscribe(published, published.bob, _INCIDENT, "2.0.0")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_subscribed"
    entry = (await published.client.get(_url(published.bob), headers=published.bob.headers)).json()[
        0
    ]
    assert entry["version"] == "1.0.0"


async def test_repinning_is_a_deliberate_act_and_is_attributed(published: ApiFixture) -> None:
    await _publish(published.client, published.alice, _INCIDENT, version="2.0.0")
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    response = await published.client.patch(
        _url(published.bob, f"/{_INCIDENT}"),
        headers=published.bob.headers,
        json={"version": "2.0.0"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "2.0.0"
    assert body["update_available"] is False
    assert body["updated_at"] is not None
    assert body["updated_by"] is not None


async def test_repinning_something_this_team_is_not_subscribed_to_is_a_404(
    published: ApiFixture,
) -> None:
    response = await published.client.patch(
        _url(published.bob, f"/{_INCIDENT}"),
        headers=published.bob.headers,
        json={"version": "1.0.0"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_subscribed"


async def test_unsubscribing_is_idempotent(published: ApiFixture) -> None:
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    first = await published.client.delete(
        _url(published.bob, f"/{_INCIDENT}"), headers=published.bob.headers
    )
    second = await published.client.delete(
        _url(published.bob, f"/{_INCIDENT}"), headers=published.bob.headers
    )
    never = await published.client.delete(
        _url(published.bob, "/never-subscribed"), headers=published.bob.headers
    )

    assert [first.status_code, second.status_code, never.status_code] == [204, 204, 204]
    assert (
        await published.client.get(_url(published.bob), headers=published.bob.headers)
    ).json() == []


async def test_unsubscribing_keeps_the_row_that_records_the_mutation(
    published: ApiFixture, database_url: str
) -> None:
    """A deleted row is an unattributable mutation. Revoking keeps the audit trail."""
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")
    await published.client.delete(
        _url(published.bob, f"/{_INCIDENT}"), headers=published.bob.headers
    )

    async with _session(database_url) as session:
        identity = await published.client.get(
            f"/api/teams/{published.bob.slug}", headers=published.bob.headers
        )
        environment_id = uuid.UUID(identity.json()["environment_id"])
        rows = await SubscriptionRepository(session).list_for_environment(
            environment_id, status=None
        )

    assert [row.status for row in rows] == [SubscriptionStatus.REVOKED]
    assert rows[0].updated_by is not None
    assert rows[0].created_by is not None


async def test_resubscribing_after_unsubscribing_works(published: ApiFixture) -> None:
    await _subscribe(published, published.bob, _INCIDENT, "1.0.0")
    await published.client.delete(
        _url(published.bob, f"/{_INCIDENT}"), headers=published.bob.headers
    )

    response = await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    assert response.status_code == 201
    assert (await published.client.get(_url(published.bob), headers=published.bob.headers)).json()[
        0
    ]["version"] == "1.0.0"


async def test_a_version_that_was_never_published_cannot_be_pinned(
    published: ApiFixture,
) -> None:
    response = await _subscribe(published, published.bob, _INCIDENT, "9.9.9")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_subscribable"


async def test_a_draft_version_cannot_be_pinned(published: ApiFixture, database_url: str) -> None:
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id(_INCIDENT)
        assert skill is not None
        await skills.add_version(
            skill, "2.0.0", "Draft.", "sha256:" + "0" * 64, status=VersionStatus.DRAFT
        )

    response = await _subscribe(published, published.bob, _INCIDENT, "2.0.0")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_subscribable"


async def test_an_archived_skill_cannot_be_pinned(published: ApiFixture, database_url: str) -> None:
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id(_INCIDENT)
        assert skill is not None
        skill.lifecycle = SkillLifecycle.ARCHIVED
        session.add(skill)

    response = await _subscribe(published, published.bob, _INCIDENT, "1.0.0")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_subscribable"


async def test_a_missing_skill_and_a_missing_version_are_indistinguishable(
    published: ApiFixture, database_url: str
) -> None:
    """`404` is chosen over `403` so that a refusal never confirms a skill exists.

    That is only true if the two refusals are also identical to each other, which is what this
    asserts and what a helpfully specific message would quietly undo.
    """
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id(_INCIDENT)
        assert skill is not None
        skill.visibility = Visibility.UNLISTED
        session.add(skill)

    absent = await _subscribe(published, published.bob, "no-such-skill", "1.0.0")
    unpublished = await _subscribe(published, published.bob, _INCIDENT, "4.5.6")

    assert absent.status_code == unpublished.status_code == 404
    assert absent.json() == unpublished.json()


async def test_an_unlisted_skill_is_still_subscribable(
    published: ApiFixture, database_url: str
) -> None:
    """Unlisted means "not advertised", not "secret" -- the same rule the catalog detail follows."""
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id(_INCIDENT)
        assert skill is not None
        skill.visibility = Visibility.UNLISTED
        session.add(skill)

    assert (await _subscribe(published, published.bob, _INCIDENT, "1.0.0")).status_code == 201


async def test_a_team_cannot_subscribe_on_behalf_of_another(published: ApiFixture) -> None:
    """The path segment is readability; the credential is the authorisation."""
    response = await published.client.post(
        _url(published.alice),
        headers=published.bob.headers,
        json={"skill_id": _INCIDENT, "version": "1.0.0"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "team_mismatch"
    assert (
        await published.client.get(_url(published.alice), headers=published.alice.headers)
    ).json() == []


async def test_a_team_cannot_read_repin_or_revoke_another_teams_subscriptions(
    published: ApiFixture,
) -> None:
    await _subscribe(published, published.alice, _PAYMENTS, "1.0.0")

    read = await published.client.get(_url(published.alice), headers=published.bob.headers)
    repin = await published.client.patch(
        _url(published.alice, f"/{_PAYMENTS}"),
        headers=published.bob.headers,
        json={"version": "1.0.0"},
    )
    revoke = await published.client.delete(
        _url(published.alice, f"/{_PAYMENTS}"), headers=published.bob.headers
    )

    assert [read.status_code, repin.status_code, revoke.status_code] == [403, 403, 403]
    assert (
        await published.client.get(_url(published.alice), headers=published.alice.headers)
    ).json()[0]["skill_id"] == _PAYMENTS


async def test_every_route_requires_a_credential(published: ApiFixture) -> None:
    slug = published.bob.slug
    responses = [
        await published.client.get(f"/api/teams/{slug}/subscriptions"),
        await published.client.post(
            f"/api/teams/{slug}/subscriptions", json={"skill_id": _INCIDENT, "version": "1.0.0"}
        ),
        await published.client.patch(
            f"/api/teams/{slug}/subscriptions/{_INCIDENT}", json={"version": "1.0.0"}
        ),
        await published.client.delete(f"/api/teams/{slug}/subscriptions/{_INCIDENT}"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]
