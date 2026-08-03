"""Identifier validation.

These patterns guard values that are interpolated into filesystem paths and URLs, so they are
applied before a value reaches the database, not only by a database constraint.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Mirrors the Agent Skills specification's `name` rule. The Hub validates it locally because the
# value is used to build store paths long before a SKILL.md exists to hand to the SDK's validator;
# tests/test_identifiers.py asserts this stays in agreement with agentskills-core.
#
# Consecutive hyphens are a separate check because the pattern alone permits them -- `a--b` matches.
SKILL_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
SKILL_ID_MAX_LEN = 64

# A team slug is a URL segment. Two characters minimum, so a single hyphen cannot appear.
TEAM_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")

# Tags arrive from publishers and leave again in `?tags=`, so they are constrained rather than
# free text: a catalog filter that depends on casing or surrounding whitespace does not work.
TAG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
TAG_MAX_LEN = 64
MAX_TAGS_PER_SKILL = 16

# The official semver.org grammar. Exact versions only, never a range -- see ADR 0003.
VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


class InvalidIdentifierError(ValueError):
    """An identifier failed validation before it could be stored or used to build a path."""


def validate_skill_id(value: str) -> str:
    if len(value) > SKILL_ID_MAX_LEN:
        raise InvalidIdentifierError(f"skill_id {value!r} exceeds {SKILL_ID_MAX_LEN} characters")
    if "--" in value:
        raise InvalidIdentifierError(f"skill_id {value!r} contains consecutive hyphens")
    if not SKILL_ID_RE.match(value):
        raise InvalidIdentifierError(
            f"skill_id {value!r} must be lowercase alphanumeric with internal hyphens"
        )
    return value


def validate_team_slug(value: str) -> str:
    if not TEAM_SLUG_RE.match(value):
        raise InvalidIdentifierError(
            f"team slug {value!r} must be 2-64 lowercase alphanumeric characters with "
            "internal hyphens"
        )
    return value


def validate_version(value: str) -> str:
    if not VERSION_RE.match(value):
        raise InvalidIdentifierError(f"version {value!r} is not a valid semantic version")
    return value


def validate_tag(value: str) -> str:
    if len(value) > TAG_MAX_LEN:
        raise InvalidIdentifierError(f"tag {value!r} exceeds {TAG_MAX_LEN} characters")
    if not TAG_RE.match(value):
        raise InvalidIdentifierError(
            f"tag {value!r} must be lowercase alphanumeric with internal hyphens"
        )
    return value


def normalise_tags(values: Iterable[str]) -> list[str]:
    """Validate, de-duplicate, and sort. Tag order is never meaningful, so it is not preserved."""
    tags = sorted({validate_tag(value.strip().lower()) for value in values})
    if len(tags) > MAX_TAGS_PER_SKILL:
        raise InvalidIdentifierError(f"a skill may carry at most {MAX_TAGS_PER_SKILL} tags")
    return tags


def version_sort_key(value: str) -> tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]:
    """Order versions by semver precedence.

    Sorting in Python rather than SQL because semver precedence is not lexicographic -- `1.10.0`
    follows `1.9.0`, and `1.0.0-rc.1` precedes `1.0.0` -- and no portable SQL expression says so.
    """
    match = VERSION_RE.match(value)
    if match is None:
        raise InvalidIdentifierError(f"version {value!r} is not a valid semantic version")

    major, minor, patch, prerelease = match.group(1, 2, 3, 4)
    if prerelease is None:
        # Build metadata is excluded from precedence by the specification, so it is not read here.
        return (int(major), int(minor), int(patch), 1, ())

    identifiers = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part) for part in prerelease.split(".")
    )
    return (int(major), int(minor), int(patch), 0, identifiers)
