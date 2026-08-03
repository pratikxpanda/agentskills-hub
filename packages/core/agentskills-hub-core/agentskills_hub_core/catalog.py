"""The catalog read model.

Separate from `repositories.py` because it answers a different question. The repositories exist to
write one row correctly; this exists to assemble the page a human decides from, which means joins,
counts, and the calling team's own subscription state in the same response. Mixing the two
produces a `SkillRepository` whose `list` method grows a parameter every time the UI changes.

Every list read is four queries regardless of page size. The alternative -- resolving versions,
tags, counts, and subscriptions per row -- is the N+1 that makes a catalog page slow exactly when
the catalog becomes worth browsing.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func
from sqlmodel import col, or_, select
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
from agentskills_hub_core.identifiers import normalise_tags, version_sort_key
from agentskills_hub_core.models import Skill, SkillTag, SkillVersion, Subscription, Team

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class InvalidCursorError(ValueError):
    """A cursor was not one this API issued."""


@dataclass(frozen=True)
class VersionSummary:
    version: str
    description: str
    content_digest: str
    catalog_tokens: int
    published_at: datetime | None
    published_by: str | None


@dataclass(frozen=True)
class CatalogEntry:
    """One row of the catalog, carrying everything the catalog page renders.

    `subscriber_count` and `is_subscribed` are the fields that turn a list of names into an answer
    to "should my team subscribe to this?", which is the only question the page exists to answer.
    """

    skill_id: str
    description: str
    owner: str
    scope: SkillScope
    lifecycle: SkillLifecycle
    subscription_model: SubscriptionModel
    tags: list[str]
    latest_version: str
    published_at: datetime | None
    subscriber_count: int
    is_subscribed: bool
    subscribed_version: str | None


@dataclass(frozen=True)
class CatalogPage:
    entries: list[CatalogEntry]
    next_cursor: str | None


@dataclass(frozen=True)
class SubscriptionView:
    """One subscription, with the facts needed to decide whether to upgrade.

    `update_available` is the compensating feature for refusing `latest` in ADR 0003: pinning is
    only reasonable if the pin's staleness is visible without going looking for it.
    """

    skill_id: str
    owner: str
    description: str
    version: str
    latest_version: str | None
    update_available: bool
    lifecycle: SkillLifecycle
    origin: SubscriptionOrigin
    subscribed_at: datetime
    subscribed_by: str | None
    updated_at: datetime | None
    updated_by: str | None


def encode_cursor(skill_id: str, row_id: uuid.UUID) -> str:
    """Opaque on purpose: the ordering it encodes is free to change without breaking clients."""
    return base64.urlsafe_b64encode(f"{skill_id}:{row_id}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        skill_id, separator, row_id = raw.partition(":")
        if not separator:
            raise ValueError(raw)
        return skill_id, uuid.UUID(row_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursorError("cursor is not one this API issued") from exc


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _published_version_exists() -> ColumnElement[bool]:
    return (
        select(SkillVersion.id)
        .where(
            col(SkillVersion.skill_id) == col(Skill.id),
            col(SkillVersion.status) == VersionStatus.PUBLISHED,
        )
        .exists()
    )


def _tag_exists(tag: str) -> ColumnElement[bool]:
    return (
        select(SkillTag.id)
        .where(col(SkillTag.skill_id) == col(Skill.id), col(SkillTag.tag) == tag)
        .exists()
    )


def _matches(query: str) -> ColumnElement[bool]:
    pattern = f"%{_escape_like(query.strip().lower())}%"
    return or_(
        func.lower(col(Skill.skill_id)).like(pattern, escape="\\"),
        select(SkillVersion.id)
        .where(
            col(SkillVersion.skill_id) == col(Skill.id),
            col(SkillVersion.status) == VersionStatus.PUBLISHED,
            func.lower(col(SkillVersion.description)).like(pattern, escape="\\"),
        )
        .exists(),
        select(SkillTag.id)
        .where(
            col(SkillTag.skill_id) == col(Skill.id),
            func.lower(col(SkillTag.tag)).like(pattern, escape="\\"),
        )
        .exists(),
    )


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_skills(
        self,
        *,
        environment_id: uuid.UUID,
        query: str | None = None,
        tags: Sequence[str] | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> CatalogPage:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        statement = (
            select(Skill, Team.slug)
            .join(Team, col(Team.id) == col(Skill.owner_team_id))
            .where(
                col(Skill.visibility) == Visibility.LISTED,
                col(Skill.lifecycle) != SkillLifecycle.ARCHIVED,
                _published_version_exists(),
            )
        )

        for tag in normalise_tags(tags or []):
            statement = statement.where(_tag_exists(tag))
        if query and query.strip():
            statement = statement.where(_matches(query))
        if cursor:
            last_skill_id, last_row_id = decode_cursor(cursor)
            # Spelled out rather than as a row-value comparison, which SQLite only learned in 3.15
            # and which several drivers still translate badly.
            statement = statement.where(
                or_(
                    col(Skill.skill_id) > last_skill_id,
                    (col(Skill.skill_id) == last_skill_id) & (col(Skill.id) > last_row_id),
                )
            )

        # One row beyond the page, so "is there more?" needs no second count query.
        statement = statement.order_by(col(Skill.skill_id), col(Skill.id)).limit(limit + 1)
        rows = list((await self._session.exec(statement)).all())

        has_more = len(rows) > limit
        rows = rows[:limit]
        entries = await self._enrich([(skill, owner) for skill, owner in rows], environment_id)
        next_cursor = (
            encode_cursor(rows[-1][0].skill_id, rows[-1][0].id) if has_more and rows else None
        )
        return CatalogPage(entries=entries, next_cursor=next_cursor)

    async def get_entry(self, skill_id: str, *, environment_id: uuid.UUID) -> CatalogEntry | None:
        """Fetch one entry by id.

        Unlisted skills are readable here but absent from `list_skills`: unlisted means "not
        advertised", not "secret". Anything genuinely private is a scope decision, not this one.
        """
        statement = (
            select(Skill, Team.slug)
            .join(Team, col(Team.id) == col(Skill.owner_team_id))
            .where(col(Skill.skill_id) == skill_id, _published_version_exists())
        )
        row = (await self._session.exec(statement)).first()
        if row is None:
            return None
        entries = await self._enrich([(row[0], row[1])], environment_id)
        return entries[0] if entries else None

    async def list_subscriptions(
        self, environment_id: uuid.UUID, *, skill_id: str | None = None
    ) -> list[SubscriptionView]:
        """Active subscriptions for one environment, newest-version information included."""
        statement = (
            select(Subscription, Skill, Team.slug)
            .join(Skill, col(Skill.id) == col(Subscription.skill_id))
            .join(Team, col(Team.id) == col(Skill.owner_team_id))
            .where(
                col(Subscription.environment_id) == environment_id,
                col(Subscription.status) == SubscriptionStatus.ACTIVE,
            )
            .order_by(col(Skill.skill_id))
        )
        if skill_id is not None:
            statement = statement.where(col(Skill.skill_id) == skill_id)
        rows = list((await self._session.exec(statement)).all())
        if not rows:
            return []

        latest = await self._latest_versions([skill.id for _, skill, _ in rows])
        views = []
        for subscription, skill, owner in rows:
            newest = latest.get(skill.id)
            views.append(
                SubscriptionView(
                    skill_id=skill.skill_id,
                    owner=owner,
                    description=newest.description if newest else "",
                    version=subscription.version,
                    latest_version=newest.version if newest else None,
                    update_available=newest is not None
                    and version_sort_key(newest.version) > version_sort_key(subscription.version),
                    lifecycle=skill.lifecycle,
                    origin=subscription.origin,
                    subscribed_at=subscription.created_at,
                    subscribed_by=subscription.created_by,
                    updated_at=subscription.updated_at,
                    updated_by=subscription.updated_by,
                )
            )
        return views

    async def get_subscription(
        self, environment_id: uuid.UUID, skill_id: str
    ) -> SubscriptionView | None:
        """One subscription, assembled the same way the list is, so the two cannot disagree."""
        views = await self.list_subscriptions(environment_id, skill_id=skill_id)
        return views[0] if views else None

    async def list_versions(self, skill: Skill) -> list[VersionSummary]:
        """Published versions, newest first by semver precedence."""
        result = await self._session.exec(
            select(SkillVersion).where(
                col(SkillVersion.skill_id) == skill.id,
                col(SkillVersion.status) == VersionStatus.PUBLISHED,
            )
        )
        ordered = sorted(result.all(), key=lambda row: version_sort_key(row.version), reverse=True)
        return [_summarise(row) for row in ordered]

    async def get_version(self, skill: Skill, version: str) -> VersionSummary | None:
        result = await self._session.exec(
            select(SkillVersion).where(
                col(SkillVersion.skill_id) == skill.id,
                col(SkillVersion.version) == version,
                col(SkillVersion.status) == VersionStatus.PUBLISHED,
            )
        )
        row = result.first()
        return _summarise(row) if row is not None else None

    async def _enrich(
        self, rows: list[tuple[Skill, str]], environment_id: uuid.UUID
    ) -> list[CatalogEntry]:
        if not rows:
            return []

        ids = [skill.id for skill, _ in rows]
        versions = await self._latest_versions(ids)
        tags = await self._tags(ids)
        counts = await self._subscriber_counts(ids)
        subscriptions = await self._subscriptions(environment_id, ids)

        entries = []
        for skill, owner in rows:
            latest = versions.get(skill.id)
            if latest is None:
                continue
            subscription = subscriptions.get(skill.id)
            entries.append(
                CatalogEntry(
                    skill_id=skill.skill_id,
                    description=latest.description,
                    owner=owner,
                    scope=skill.scope,
                    lifecycle=skill.lifecycle,
                    subscription_model=skill.subscription_model,
                    tags=tags.get(skill.id, []),
                    latest_version=latest.version,
                    published_at=latest.published_at,
                    subscriber_count=counts.get(skill.id, 0),
                    is_subscribed=subscription is not None,
                    subscribed_version=subscription.version if subscription else None,
                )
            )
        return entries

    async def _latest_versions(
        self, skill_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, VersionSummary]:
        result = await self._session.exec(
            select(SkillVersion).where(
                col(SkillVersion.skill_id).in_(skill_ids),
                col(SkillVersion.status) == VersionStatus.PUBLISHED,
            )
        )
        latest: dict[uuid.UUID, SkillVersion] = {}
        for row in result.all():
            current = latest.get(row.skill_id)
            if current is None or version_sort_key(row.version) > version_sort_key(current.version):
                latest[row.skill_id] = row
        return {skill_id: _summarise(row) for skill_id, row in latest.items()}

    async def _tags(self, skill_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        result = await self._session.exec(
            select(SkillTag)
            .where(col(SkillTag.skill_id).in_(skill_ids))
            .order_by(col(SkillTag.tag))
        )
        tags: dict[uuid.UUID, list[str]] = {}
        for row in result.all():
            tags.setdefault(row.skill_id, []).append(row.tag)
        return tags

    async def _subscriber_counts(self, skill_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        statement = (
            select(col(Subscription.skill_id), func.count())
            .where(
                col(Subscription.skill_id).in_(skill_ids),
                col(Subscription.status) == SubscriptionStatus.ACTIVE,
            )
            .group_by(col(Subscription.skill_id))
        )
        return {skill_id: count for skill_id, count in (await self._session.exec(statement)).all()}

    async def _subscriptions(
        self, environment_id: uuid.UUID, skill_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, Subscription]:
        result = await self._session.exec(
            select(Subscription).where(
                col(Subscription.environment_id) == environment_id,
                col(Subscription.skill_id).in_(skill_ids),
                col(Subscription.status) == SubscriptionStatus.ACTIVE,
            )
        )
        return {row.skill_id: row for row in result.all()}


def _summarise(row: SkillVersion) -> VersionSummary:
    return VersionSummary(
        version=row.version,
        description=row.description,
        content_digest=row.content_digest,
        catalog_tokens=row.catalog_tokens,
        published_at=row.published_at,
        published_by=row.published_by,
    )


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "CatalogEntry",
    "CatalogPage",
    "CatalogRepository",
    "InvalidCursorError",
    "SubscriptionView",
    "VersionSummary",
    "decode_cursor",
    "encode_cursor",
]
