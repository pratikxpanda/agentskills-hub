"""Persistence model.

Columns that later milestones need are present and discriminated rather than absent: `scope` only
ever holds `org` in v0.1, but adding it later would be a migration plus a backfill.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, Enum, UniqueConstraint
from sqlmodel import Field, SQLModel

from agentskills_hub_core.enums import (
    SkillLifecycle,
    SkillScope,
    SubscriptionModel,
    SubscriptionOrigin,
    SubscriptionStatus,
    VersionStatus,
    Visibility,
)
from agentskills_hub_core.types import UtcDateTime, utcnow


def _enum_column(enum_type: type, name: str) -> Column:  # type: ignore[type-arg]
    # native_enum=False keeps this a VARCHAR + CHECK, which SQLite can alter and Postgres accepts.
    return Column(
        Enum(
            enum_type, name=name, native_enum=False, values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )


class Team(SQLModel, table=True):
    __tablename__ = "team"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    slug: str = Field(unique=True, index=True, max_length=64)
    name: str = Field(max_length=200)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UtcDateTime)


class Environment(SQLModel, table=True):
    __tablename__ = "environment"
    __table_args__ = (UniqueConstraint("team_id", "name", name="uq_environment_team_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    name: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UtcDateTime)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_key"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    # The key identifies the environment as well as the team, because that is what the gateway
    # resolves from the credential rather than from the URL.
    environment_id: uuid.UUID = Field(foreign_key="environment.id", index=True)
    prefix: str = Field(unique=True, index=True, max_length=16)
    key_hash: str = Field(max_length=128)
    created_at: datetime = Field(default_factory=utcnow, sa_type=UtcDateTime)
    last_used_at: datetime | None = Field(default=None, sa_type=UtcDateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=UtcDateTime)


class Skill(SQLModel, table=True):
    __tablename__ = "skill"
    __table_args__ = (
        UniqueConstraint("skill_id", "scope", "owner_team_id", name="uq_skill_identity"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    skill_id: str = Field(index=True, max_length=64)
    scope: SkillScope = Field(sa_column=_enum_column(SkillScope, "skill_scope"))
    owner_team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    visibility: Visibility = Field(sa_column=_enum_column(Visibility, "visibility"))
    subscription_model: SubscriptionModel = Field(
        sa_column=_enum_column(SubscriptionModel, "subscription_model")
    )
    lifecycle: SkillLifecycle = Field(sa_column=_enum_column(SkillLifecycle, "skill_lifecycle"))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, sa_type=UtcDateTime)


class SkillVersion(SQLModel, table=True):
    __tablename__ = "skill_version"
    __table_args__ = (UniqueConstraint("skill_id", "version", name="uq_skill_version"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    skill_id: uuid.UUID = Field(foreign_key="skill.id", index=True)
    version: str = Field(max_length=64)
    description: str = Field(max_length=1024)
    # SHA-256 over the version's file tree, computed at publish. The anchor for integrity
    # verification later; it cannot be backfilled honestly.
    content_digest: str = Field(max_length=64)
    # Measured cost of this version's catalog entry, so a team's prompt cost is a number the Hub
    # displays rather than estimates.
    catalog_tokens: int = Field(default=0)
    status: VersionStatus = Field(sa_column=_enum_column(VersionStatus, "version_status"))
    published_at: datetime | None = Field(default=None, sa_type=UtcDateTime)
    published_by: str | None = Field(default=None, max_length=200)


class Subscription(SQLModel, table=True):
    __tablename__ = "subscription"
    __table_args__ = (
        UniqueConstraint("environment_id", "skill_id", name="uq_subscription_environment_skill"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    environment_id: uuid.UUID = Field(foreign_key="environment.id", index=True)
    skill_id: uuid.UUID = Field(foreign_key="skill.id", index=True)
    version: str = Field(max_length=64)
    origin: SubscriptionOrigin = Field(
        sa_column=_enum_column(SubscriptionOrigin, "subscription_origin")
    )
    status: SubscriptionStatus = Field(
        sa_column=_enum_column(SubscriptionStatus, "subscription_status")
    )
    created_at: datetime = Field(default_factory=utcnow, sa_type=UtcDateTime)


__all__ = [
    "ApiKey",
    "Environment",
    "Skill",
    "SkillVersion",
    "Subscription",
    "Team",
]
