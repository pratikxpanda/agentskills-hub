"""Enumerations from DESIGN.md.

`SkillLifecycle` applies to a skill and all of its versions at once; `VersionStatus` applies to a
single version. They are deliberately separate types -- collapsing them is the schema mistake this
milestone is most likely to make.
"""

from __future__ import annotations

from enum import StrEnum


class SkillScope(StrEnum):
    ORG = "org"
    DOMAIN = "domain"
    TEAM = "team"


class Visibility(StrEnum):
    LISTED = "listed"
    UNLISTED = "unlisted"


class SubscriptionModel(StrEnum):
    OPEN = "open"
    APPROVAL_REQUIRED = "approval-required"


class SkillLifecycle(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class SubscriptionOrigin(StrEnum):
    MANUAL = "manual"
    COLLECTION = "collection"
    POLICY = "policy"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PENDING_APPROVAL = "pending-approval"
    REVOKED = "revoked"
