"""Repository behaviour, including the invariants the schema alone cannot express."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_core.enums import (
    SkillLifecycle,
    SkillScope,
    SubscriptionModel,
    SubscriptionOrigin,
    SubscriptionStatus,
    VersionStatus,
    Visibility,
)
from agentskills_hub_core.identifiers import InvalidIdentifierError
from agentskills_hub_core.models import Team
from agentskills_hub_core.repositories import (
    DEFAULT_ENVIRONMENT_NAME,
    ApiKeyRepository,
    SkillRepository,
    SubscriptionRepository,
    TeamRepository,
)
from agentskills_hub_core.types import UtcDateTime

DIGEST = "0" * 64


async def test_creating_a_team_creates_its_default_environment(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, environment = await teams.create("checkout-squad", "Checkout Squad")
    await session.commit()

    assert environment.team_id == team.id
    assert environment.name == DEFAULT_ENVIRONMENT_NAME
    assert await teams.default_environment(team.id) is not None


async def test_team_and_environment_are_created_in_one_transaction(
    session: AsyncSession,
) -> None:
    teams = TeamRepository(session)
    await teams.create("checkout-squad", "Checkout Squad")
    # A duplicate slug fails at flush; the environment from the first call must not survive
    # independently of its team.
    with pytest.raises(IntegrityError):
        await teams.create("checkout-squad", "Duplicate")
        await session.commit()
    await session.rollback()

    assert await teams.get_by_slug("checkout-squad") is None


async def test_team_slug_is_validated_before_the_database(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    with pytest.raises(InvalidIdentifierError):
        await teams.create("Not A Slug", "Invalid")


async def test_team_slug_is_unique(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    await teams.create("platform-team", "Platform")
    await session.commit()
    with pytest.raises(IntegrityError):
        await teams.create("platform-team", "Platform Again")
        await session.commit()


async def test_timestamps_round_trip_as_aware_utc(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    await session.commit()
    session.expunge_all()

    stored = await session.get(Team, team.id)
    assert stored is not None
    assert stored.created_at.tzinfo is not None
    assert stored.created_at.utcoffset() == timedelta(0)
    assert (datetime.now(UTC) - stored.created_at).total_seconds() < 60


def test_naive_timestamps_are_rejected() -> None:
    # A naive value would be stored as if it were UTC and read back claiming to be UTC, which is
    # how a timezone bug survives a test suite.
    with pytest.raises(ValueError, match="naive datetime"):
        UtcDateTime().process_bind_param(
            datetime(2026, 1, 1, 12, 0, 0),
            sqlite_dialect(),
        )


def test_aware_timestamps_are_normalised_to_utc() -> None:
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    bound = UtcDateTime().process_bind_param(aware, sqlite_dialect())
    assert bound == datetime(2026, 1, 1, 6, 30, 0)
    assert UtcDateTime().process_result_value(bound, sqlite_dialect()) == aware


async def test_api_key_identifies_team_and_environment(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, environment = await teams.create("platform-team", "Platform")
    keys = ApiKeyRepository(session)
    created = await keys.create(team.id, environment.id, "hub_abc123", "hash")
    await session.commit()

    found = await keys.get_by_prefix("hub_abc123")
    assert found is not None
    assert found.id == created.id
    assert found.team_id == team.id
    assert found.environment_id == environment.id
    assert found.last_used_at is None
    assert found.revoked_at is None

    await keys.mark_used(found.id)
    await keys.revoke(found.id)
    await session.commit()

    refreshed = await keys.get_by_prefix("hub_abc123")
    assert refreshed is not None
    assert refreshed.last_used_at is not None
    assert refreshed.revoked_at is not None


async def test_skill_lifecycle_and_version_status_are_independent(
    session: AsyncSession,
) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id, tags=["payments", "compliance"])
    published = await skills.add_version(skill, "1.0.0", "Reviews payment code.", DIGEST)
    draft = await skills.add_version(
        skill, "2.0.0", "Next revision.", DIGEST, status=VersionStatus.DRAFT
    )
    await session.commit()

    # The skill is active while one of its versions is published and another is a draft: two
    # columns, two enums, no collapsing.
    assert skill.lifecycle is SkillLifecycle.ACTIVE
    assert published.status is VersionStatus.PUBLISHED
    assert published.published_at is not None
    assert draft.status is VersionStatus.DRAFT
    assert draft.published_at is None


async def test_v01_defaults_match_the_milestone(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    await session.commit()

    assert skill.scope is SkillScope.ORG
    assert skill.visibility is Visibility.LISTED
    assert skill.subscription_model is SubscriptionModel.OPEN
    assert skill.lifecycle is SkillLifecycle.ACTIVE
    assert skill.tags == []


async def test_skill_id_is_validated_before_the_database(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    with pytest.raises(InvalidIdentifierError):
        await skills.create("Not A Skill Id", team.id)


async def test_skill_version_pair_is_unique(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    await skills.add_version(skill, "1.0.0", "First.", DIGEST)
    await session.commit()

    with pytest.raises(IntegrityError):
        await skills.add_version(skill, "1.0.0", "Duplicate.", DIGEST)
        await session.commit()


async def test_version_is_validated_before_the_database(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    with pytest.raises(InvalidIdentifierError):
        await skills.add_version(skill, "^1.0.0", "A range, not a version.", DIGEST)


async def test_catalog_tokens_and_digest_are_recorded(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, _ = await teams.create("platform-team", "Platform")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    version = await skills.add_version(
        skill, "1.0.0", "Reviews payment code.", DIGEST, catalog_tokens=42, published_by="ada"
    )
    await session.commit()

    stored = await skills.get_version(skill.id, "1.0.0")
    assert stored is not None
    assert stored.content_digest == version.content_digest
    assert stored.catalog_tokens == 42
    assert stored.published_by == "ada"


async def test_one_subscription_per_skill_per_environment(session: AsyncSession) -> None:
    teams = TeamRepository(session)
    team, environment = await teams.create("checkout-squad", "Checkout Squad")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    await skills.add_version(skill, "1.0.0", "Reviews payment code.", DIGEST)

    subscriptions = SubscriptionRepository(session)
    subscription = await subscriptions.subscribe(team.id, environment.id, skill.id, "1.0.0")
    await session.commit()

    assert subscription.origin is SubscriptionOrigin.MANUAL
    assert subscription.status is SubscriptionStatus.ACTIVE

    with pytest.raises(IntegrityError):
        await subscriptions.subscribe(team.id, environment.id, skill.id, "2.0.0")
        await session.commit()


async def test_subscriptions_are_listed_and_removed_by_environment(
    session: AsyncSession,
) -> None:
    teams = TeamRepository(session)
    team, environment = await teams.create("checkout-squad", "Checkout Squad")
    skills = SkillRepository(session)
    skill = await skills.create("pci-payment-review", team.id)
    await skills.add_version(skill, "1.0.0", "Reviews payment code.", DIGEST)

    subscriptions = SubscriptionRepository(session)
    await subscriptions.subscribe(team.id, environment.id, skill.id, "1.0.0")
    await session.commit()

    assert len(await subscriptions.list_for_environment(environment.id)) == 1
    assert await subscriptions.unsubscribe(environment.id, skill.id) is True
    await session.commit()
    assert await subscriptions.list_for_environment(environment.id) == []
    assert await subscriptions.unsubscribe(environment.id, uuid.uuid4()) is False
