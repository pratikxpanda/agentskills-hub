"""Repositories.

All reads and writes go through these classes. No ORM session is exposed above `core`; the
import-linter contract `no ORM session escapes core` enforces that mechanically.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import select
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
from agentskills_hub_core.identifiers import (
    validate_skill_id,
    validate_team_slug,
    validate_version,
)
from agentskills_hub_core.models import (
    ApiKey,
    Environment,
    Skill,
    SkillVersion,
    Subscription,
    Team,
)
from agentskills_hub_core.types import utcnow

DEFAULT_ENVIRONMENT_NAME = "default"


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, slug: str, name: str) -> tuple[Team, Environment]:
        """Create a team and its default environment in one transaction.

        A team without an environment cannot hold subscriptions, so the two are never separate.
        """
        validate_team_slug(slug)
        team = Team(slug=slug, name=name)
        self._session.add(team)
        await self._session.flush()

        environment = Environment(team_id=team.id, name=DEFAULT_ENVIRONMENT_NAME)
        self._session.add(environment)
        await self._session.flush()
        return team, environment

    async def get_by_slug(self, slug: str) -> Team | None:
        result = await self._session.exec(select(Team).where(Team.slug == slug))
        return result.first()

    async def list_all(self) -> list[Team]:
        result = await self._session.exec(select(Team).order_by(Team.slug))
        return list(result.all())

    async def default_environment(self, team_id: uuid.UUID) -> Environment | None:
        result = await self._session.exec(
            select(Environment).where(
                Environment.team_id == team_id,
                Environment.name == DEFAULT_ENVIRONMENT_NAME,
            )
        )
        return result.first()


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        team_id: uuid.UUID,
        environment_id: uuid.UUID,
        prefix: str,
        key_hash: str,
    ) -> ApiKey:
        key = ApiKey(
            team_id=team_id,
            environment_id=environment_id,
            prefix=prefix,
            key_hash=key_hash,
        )
        self._session.add(key)
        await self._session.flush()
        return key

    async def get_by_prefix(self, prefix: str) -> ApiKey | None:
        result = await self._session.exec(select(ApiKey).where(ApiKey.prefix == prefix))
        return result.first()

    async def mark_used(self, key_id: uuid.UUID, when: datetime | None = None) -> None:
        key = await self._session.get(ApiKey, key_id)
        if key is not None:
            key.last_used_at = when or utcnow()
            self._session.add(key)

    async def revoke(self, key_id: uuid.UUID, when: datetime | None = None) -> None:
        key = await self._session.get(ApiKey, key_id)
        if key is not None:
            key.revoked_at = when or utcnow()
            self._session.add(key)


class SkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        skill_id: str,
        owner_team_id: uuid.UUID,
        *,
        scope: SkillScope = SkillScope.ORG,
        visibility: Visibility = Visibility.LISTED,
        subscription_model: SubscriptionModel = SubscriptionModel.OPEN,
        lifecycle: SkillLifecycle = SkillLifecycle.ACTIVE,
        tags: list[str] | None = None,
    ) -> Skill:
        validate_skill_id(skill_id)
        skill = Skill(
            skill_id=skill_id,
            owner_team_id=owner_team_id,
            scope=scope,
            visibility=visibility,
            subscription_model=subscription_model,
            lifecycle=lifecycle,
            tags=tags or [],
        )
        self._session.add(skill)
        await self._session.flush()
        return skill

    async def get_by_skill_id(self, skill_id: str) -> Skill | None:
        result = await self._session.exec(select(Skill).where(Skill.skill_id == skill_id))
        return result.first()

    async def list_all(self) -> list[Skill]:
        result = await self._session.exec(select(Skill).order_by(Skill.skill_id))
        return list(result.all())

    async def add_version(
        self,
        skill: Skill,
        version: str,
        description: str,
        content_digest: str,
        *,
        catalog_tokens: int = 0,
        status: VersionStatus = VersionStatus.PUBLISHED,
        published_by: str | None = None,
    ) -> SkillVersion:
        validate_version(version)
        skill_version = SkillVersion(
            skill_id=skill.id,
            version=version,
            description=description,
            content_digest=content_digest,
            catalog_tokens=catalog_tokens,
            status=status,
            published_at=utcnow() if status is VersionStatus.PUBLISHED else None,
            published_by=published_by,
        )
        self._session.add(skill_version)
        await self._session.flush()
        return skill_version

    async def get_version(self, skill_id: uuid.UUID, version: str) -> SkillVersion | None:
        result = await self._session.exec(
            select(SkillVersion).where(
                SkillVersion.skill_id == skill_id,
                SkillVersion.version == version,
            )
        )
        return result.first()

    async def list_versions(self, skill_id: uuid.UUID) -> list[SkillVersion]:
        result = await self._session.exec(
            select(SkillVersion).where(SkillVersion.skill_id == skill_id)
        )
        return list(result.all())


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def subscribe(
        self,
        team_id: uuid.UUID,
        environment_id: uuid.UUID,
        skill_id: uuid.UUID,
        version: str,
        *,
        origin: SubscriptionOrigin = SubscriptionOrigin.MANUAL,
        status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    ) -> Subscription:
        validate_version(version)
        subscription = Subscription(
            team_id=team_id,
            environment_id=environment_id,
            skill_id=skill_id,
            version=version,
            origin=origin,
            status=status,
        )
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    async def list_for_environment(self, environment_id: uuid.UUID) -> list[Subscription]:
        result = await self._session.exec(
            select(Subscription).where(Subscription.environment_id == environment_id)
        )
        return list(result.all())

    async def get(self, environment_id: uuid.UUID, skill_id: uuid.UUID) -> Subscription | None:
        result = await self._session.exec(
            select(Subscription).where(
                Subscription.environment_id == environment_id,
                Subscription.skill_id == skill_id,
            )
        )
        return result.first()

    async def unsubscribe(self, environment_id: uuid.UUID, skill_id: uuid.UUID) -> bool:
        subscription = await self.get(environment_id, skill_id)
        if subscription is None:
            return False
        await self._session.delete(subscription)
        return True


__all__ = [
    "DEFAULT_ENVIRONMENT_NAME",
    "ApiKeyRepository",
    "SkillRepository",
    "SubscriptionRepository",
    "TeamRepository",
]
