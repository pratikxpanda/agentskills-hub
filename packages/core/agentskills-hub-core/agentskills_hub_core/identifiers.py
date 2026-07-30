"""Identifier validation.

These patterns guard values that are interpolated into filesystem paths and URLs, so they are
applied before a value reaches the database, not only by a database constraint.
"""

from __future__ import annotations

import re

# Mirrors the Agent Skills specification's `name` rule. The Hub validates it locally because the
# value is used to build store paths long before a SKILL.md exists to hand to the SDK's validator;
# tests/test_identifiers.py asserts this stays in agreement with agentskills-core.
#
# Consecutive hyphens are a separate check because the pattern alone permits them -- `a--b` matches.
SKILL_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
SKILL_ID_MAX_LEN = 64

# A team slug is a URL segment. Two characters minimum, so a single hyphen cannot appear.
TEAM_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")

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
