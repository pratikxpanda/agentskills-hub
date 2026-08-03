"""The catalog.

The list endpoint is asserted field by field rather than by shape. It is the contract two
consumers render from -- the UI in item 9 and the CLI in v0.2 -- and the failure it is written
against is a response that looks fine and forces every client to fetch each row again.
"""

from __future__ import annotations

import io
import tarfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest_asyncio
from httpx import AsyncClient, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_core import (
    SkillRepository,
    SubscriptionRepository,
    VersionStatus,
    Visibility,
    create_engine,
    create_session_factory,
    session_scope,
)
from conftest import ApiFixture, Credential, skill_markdown

_FIELDS = {
    "skill_id",
    "description",
    "owner",
    "scope",
    "lifecycle",
    "subscription_model",
    "tags",
    "latest_version",
    "published_at",
    "subscriber_count",
    "is_subscribed",
    "subscribed_version",
}


def _archive(
    skill_id: str, description: str | None = None, extra: dict[str, bytes] | None = None
) -> bytes:
    markdown = (
        skill_markdown(skill_id, description=description)
        if description
        else skill_markdown(skill_id)
    )
    files = {f"{skill_id}/SKILL.md": markdown.encode(), **(extra or {})}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


async def _publish(
    client: AsyncClient,
    credential: Credential,
    skill_id: str,
    *,
    version: str = "1.0.0",
    tags: str | None = None,
    description: str | None = None,
    extra: dict[str, bytes] | None = None,
) -> Response:
    data = {"skill_id": skill_id, "version": version}
    if tags is not None:
        data["tags"] = tags
    return await client.post(
        "/api/skills",
        headers=credential.headers,
        data=data,
        files={
            "archive": (
                "skill.tar.gz",
                _archive(skill_id, description, extra),
                "application/gzip",
            )
        },
    )


@asynccontextmanager
async def _session(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session outside the app, for state no endpoint can create yet.

    Drafts and subscriptions arrive in items 7 and later. Seeding them directly is what lets the
    listing rules be tested now rather than after the endpoints that would produce them.
    """
    engine = create_engine(database_url)
    try:
        async with session_scope(create_session_factory(engine)) as session:
            yield session
    finally:
        await engine.dispose()


async def _identity(api: ApiFixture, credential: Credential) -> dict[str, str]:
    response = await api.client.get(f"/api/teams/{credential.slug}", headers=credential.headers)
    return dict(response.json())


@pytest_asyncio.fixture
async def catalog(api: ApiFixture, database_url: str) -> ApiFixture:
    await _publish(
        api.client,
        api.alice,
        "incident-response",
        tags='["oncall", "sre"]',
        description="Guides an on-call engineer through triage and handover.",
    )
    await _publish(
        api.client,
        api.bob,
        "pci-payment-review",
        tags='["payments", "compliance"]',
        description="Reviews changes to payment code against PCI scope.",
    )
    return api


async def test_the_page_a_client_renders_needs_exactly_one_request(catalog: ApiFixture) -> None:
    response = await catalog.client.get("/api/skills", headers=catalog.alice.headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    for item in items:
        assert set(item) == _FIELDS
    entry = items[0]
    assert entry["skill_id"] == "incident-response"
    assert entry["description"].startswith("Guides an on-call engineer")
    assert entry["owner"] == "checkout-squad"
    assert entry["scope"] == "org"
    assert entry["tags"] == ["oncall", "sre"]
    assert entry["latest_version"] == "1.0.0"
    assert entry["published_at"] is not None
    assert entry["subscriber_count"] == 0


async def test_the_catalog_is_ordered_and_owned(catalog: ApiFixture) -> None:
    response = await catalog.client.get("/api/skills", headers=catalog.alice.headers)

    items = response.json()["items"]
    assert [item["skill_id"] for item in items] == ["incident-response", "pci-payment-review"]
    assert [item["owner"] for item in items] == ["checkout-squad", "platform-team"]


async def test_latest_version_is_semver_not_lexicographic(catalog: ApiFixture) -> None:
    await _publish(catalog.client, catalog.alice, "incident-response", version="1.9.0")
    await _publish(catalog.client, catalog.alice, "incident-response", version="1.10.0")

    response = await catalog.client.get(
        "/api/skills/incident-response", headers=catalog.alice.headers
    )

    # 1.9.0 sorts after 1.10.0 as a string, which is the bug this asserts against.
    assert response.json()["latest_version"] == "1.10.0"


async def test_unpublished_versions_never_reach_the_catalog(
    catalog: ApiFixture, database_url: str
) -> None:
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id("incident-response")
        assert skill is not None
        for version, state in (
            ("2.0.0", VersionStatus.DRAFT),
            ("3.0.0", VersionStatus.DEPRECATED),
            ("4.0.0", VersionStatus.ARCHIVED),
        ):
            await skills.add_version(skill, version, "Later.", "d" * 64, status=state)

    listing = await catalog.client.get("/api/skills", headers=catalog.alice.headers)
    versions = await catalog.client.get(
        "/api/skills/incident-response/versions", headers=catalog.alice.headers
    )

    assert listing.json()["items"][0]["latest_version"] == "1.0.0"
    assert [item["version"] for item in versions.json()] == ["1.0.0"]


async def test_a_skill_with_no_published_version_is_not_listed(
    catalog: ApiFixture, database_url: str
) -> None:
    async with _session(database_url) as session:
        skills = SkillRepository(session)
        skill = await skills.get_by_skill_id("incident-response")
        assert skill is not None
        draft = await skills.create("draft-only", skill.owner_team_id)
        await skills.add_version(draft, "1.0.0", "Not ready.", "d" * 64, status=VersionStatus.DRAFT)

    listing = await catalog.client.get("/api/skills", headers=catalog.alice.headers)
    detail = await catalog.client.get("/api/skills/draft-only", headers=catalog.alice.headers)

    assert "draft-only" not in [item["skill_id"] for item in listing.json()["items"]]
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "skill_not_found"


async def test_subscription_state_is_the_calling_teams_own(
    catalog: ApiFixture, database_url: str
) -> None:
    identity = await _identity(catalog, catalog.alice)
    async with _session(database_url) as session:
        skill = await SkillRepository(session).get_by_skill_id("incident-response")
        assert skill is not None
        await SubscriptionRepository(session).subscribe(
            uuid.UUID(identity["team_id"]),
            uuid.UUID(identity["environment_id"]),
            skill.id,
            "1.0.0",
        )

    mine = await catalog.client.get("/api/skills", headers=catalog.alice.headers)
    theirs = await catalog.client.get("/api/skills", headers=catalog.bob.headers)

    subscribed = mine.json()["items"][0]
    assert subscribed["is_subscribed"] is True
    assert subscribed["subscribed_version"] == "1.0.0"
    assert subscribed["subscriber_count"] == 1

    # Team B sees the same skill and the same count, but never team A's subscription as its own.
    other = theirs.json()["items"][0]
    assert other["is_subscribed"] is False
    assert other["subscribed_version"] is None
    assert other["subscriber_count"] == 1


async def test_q_matches_the_id(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"q": "payment"}
    )

    assert [item["skill_id"] for item in response.json()["items"]] == ["pci-payment-review"]


async def test_q_matches_the_description(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"q": "handover"}
    )

    assert [item["skill_id"] for item in response.json()["items"]] == ["incident-response"]


async def test_q_matches_a_tag(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"q": "compliance"}
    )

    assert [item["skill_id"] for item in response.json()["items"]] == ["pci-payment-review"]


async def test_q_does_not_let_a_wildcard_through(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"q": "%"}
    )

    # An unescaped LIKE pattern would match everything.
    assert response.json()["items"] == []


async def test_tag_filtering_is_and_not_or(catalog: ApiFixture) -> None:
    both = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params=[("tags", "oncall"), ("tags", "sre")]
    )
    mixed = await catalog.client.get(
        "/api/skills",
        headers=catalog.alice.headers,
        params=[("tags", "oncall"), ("tags", "payments")],
    )

    assert [item["skill_id"] for item in both.json()["items"]] == ["incident-response"]
    assert mixed.json()["items"] == []


async def test_a_tag_filter_does_not_match_a_longer_tag(catalog: ApiFixture) -> None:
    await _publish(catalog.client, catalog.alice, "deploy-guard", tags='["devops"]')

    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"tags": "ops"}
    )

    # The substring match a JSON tags column would force on us matches `ops` inside `devops`.
    assert response.json()["items"] == []


async def test_pagination_is_stable_when_a_row_is_inserted_behind_the_cursor(
    catalog: ApiFixture,
) -> None:
    for skill_id in ("alpha-skill", "bravo-skill", "delta-skill"):
        await _publish(catalog.client, catalog.alice, skill_id)

    first = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"limit": 2}
    )
    seen = [item["skill_id"] for item in first.json()["items"]]
    cursor = first.json()["next_cursor"]
    assert seen == ["alpha-skill", "bravo-skill"]
    assert cursor is not None

    # Sorts before the cursor, so an offset-based page two would repeat a row and skip another.
    await _publish(catalog.client, catalog.alice, "aardvark-skill")

    second = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"limit": 2, "cursor": cursor}
    )
    rest = [item["skill_id"] for item in second.json()["items"]]

    assert rest == ["delta-skill", "incident-response"]
    assert not set(seen) & set(rest)


async def test_a_cursor_this_api_did_not_issue_is_refused(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills", headers=catalog.alice.headers, params={"cursor": "not-a-cursor"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


async def test_detail_returns_markdown_and_the_resource_inventory(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills/incident-response", headers=catalog.alice.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == _FIELDS | {"body", "resources"}
    assert body["body"].startswith("## Triage")
    assert body["resources"] == {}


async def test_the_inventory_lists_what_was_published_beside_the_skill(
    catalog: ApiFixture,
) -> None:
    await _publish(
        catalog.client,
        catalog.alice,
        "runbook-skill",
        extra={
            "runbook-skill/references/escalation.md": b"# Escalation\n",
            "runbook-skill/scripts/page.sh": b"#!/bin/sh\n",
        },
    )

    response = await catalog.client.get("/api/skills/runbook-skill", headers=catalog.alice.headers)

    assert response.json()["resources"] == {
        "references": ["escalation.md"],
        "scripts": ["page.sh"],
    }


async def test_no_endpoint_returns_html(catalog: ApiFixture) -> None:
    await _publish(
        catalog.client, catalog.alice, "xss-probe", description="A description with <b>markup</b>."
    )

    detail = await catalog.client.get("/api/skills/xss-probe", headers=catalog.alice.headers)
    version = await catalog.client.get(
        "/api/skills/xss-probe/versions/1.0.0", headers=catalog.alice.headers
    )

    for response in (detail, version):
        assert response.headers["content-type"].startswith("application/json")
        # The markdown is returned verbatim; nothing on this path renders it.
        assert "<b>markup</b>" in response.json()["description"]
        assert response.json()["body"] == "## Triage\n\nStart with the alert."


async def test_versions_are_newest_first(catalog: ApiFixture) -> None:
    for version in ("1.0.1", "2.0.0", "1.5.0"):
        await _publish(catalog.client, catalog.alice, "incident-response", version=version)

    response = await catalog.client.get(
        "/api/skills/incident-response/versions", headers=catalog.alice.headers
    )

    assert [item["version"] for item in response.json()] == ["2.0.0", "1.5.0", "1.0.1", "1.0.0"]


async def test_one_version_carries_its_own_body_and_digest(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills/incident-response/versions/1.0.0", headers=catalog.alice.headers
    )

    body = response.json()
    assert body["version"] == "1.0.0"
    assert body["skill_id"] == "incident-response"
    assert len(body["content_digest"]) == 64
    assert body["published_by"] == "checkout-squad"
    assert body["body"].startswith("## Triage")


async def test_an_unpublished_version_is_not_readable(catalog: ApiFixture) -> None:
    response = await catalog.client.get(
        "/api/skills/incident-response/versions/9.9.9", headers=catalog.alice.headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "version_not_found"


async def test_an_unlisted_skill_is_hidden_from_the_list_but_readable_by_id(
    catalog: ApiFixture, database_url: str
) -> None:
    async with _session(database_url) as session:
        skill = await SkillRepository(session).get_by_skill_id("pci-payment-review")
        assert skill is not None
        skill.visibility = Visibility.UNLISTED
        session.add(skill)

    listing = await catalog.client.get("/api/skills", headers=catalog.alice.headers)
    detail = await catalog.client.get(
        "/api/skills/pci-payment-review", headers=catalog.alice.headers
    )

    assert [item["skill_id"] for item in listing.json()["items"]] == ["incident-response"]
    assert detail.status_code == 200


async def test_every_catalog_endpoint_requires_a_credential(catalog: ApiFixture) -> None:
    paths = (
        "/api/skills",
        "/api/skills/incident-response",
        "/api/skills/incident-response/versions",
        "/api/skills/incident-response/versions/1.0.0",
    )

    for path in paths:
        response = await catalog.client.get(path)
        assert response.status_code == 401, path
