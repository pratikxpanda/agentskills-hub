"""Identifiers are validated before they reach the database."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentskills_core import Skill, validate_skill
from agentskills_fs import LocalFileSystemSkillProvider

from agentskills_hub_core.identifiers import (
    InvalidIdentifierError,
    validate_skill_id,
    validate_team_slug,
    validate_version,
)

VALID_SKILL_IDS = ["a", "pci-payment-review", "a1", "incident-response-2"]
INVALID_SKILL_IDS = [
    "",
    "-leading",
    "trailing-",
    "Upper",
    "has_underscore",
    "has space",
    "double--hyphen",
    "a" * 65,
]


@pytest.mark.parametrize("value", VALID_SKILL_IDS)
def test_valid_skill_ids_pass(value: str) -> None:
    assert validate_skill_id(value) == value


@pytest.mark.parametrize("value", INVALID_SKILL_IDS)
def test_invalid_skill_ids_raise(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_skill_id(value)


async def test_skill_id_rule_agrees_with_the_sdk(tmp_path: Path) -> None:
    """Catch drift from agentskills-core's `name` rule.

    ADR 0001 says the Hub implements none of the SDK. It validates `skill_id` locally anyway,
    because the value builds store paths before any SKILL.md exists -- so this test pins the two
    rules together rather than trusting a copied comment.
    """
    root = tmp_path / "skills"
    # The SDK reaches its name rule only via a skill on disk, and its "name matches skill_id" rule
    # requires the directory to be named after the value. Two values cannot take part: the empty
    # string cannot name a directory, and a case-insensitive filesystem cannot distinguish "Upper".
    not_comparable = {"", "Upper"}
    comparable = [
        value for value in VALID_SKILL_IDS + INVALID_SKILL_IDS if value not in not_comparable
    ]

    for value in comparable:
        skill_dir = root / value
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f'---\nname: "{value}"\n'
            "description: A probe skill used to compare validation rules.\n---\n\nBody.\n",
            encoding="utf-8",
        )
        skill = Skill(skill_id=value, provider=LocalFileSystemSkillProvider(root))
        sdk_errors = await validate_skill(skill)
        sdk_rejects_name = any("name" in error for error in sdk_errors)

        try:
            validate_skill_id(value)
        except InvalidIdentifierError:
            hub_rejects = True
        else:
            hub_rejects = False

        assert hub_rejects == sdk_rejects_name, (
            f"{value!r}: hub rejects={hub_rejects}, sdk rejects={sdk_rejects_name} ({sdk_errors})"
        )


@pytest.mark.parametrize("value", ["ab", "checkout-squad", "a0", "b" * 64])
def test_valid_team_slugs_pass(value: str) -> None:
    assert validate_team_slug(value) == value


@pytest.mark.parametrize("value", ["", "a", "-ab", "ab-", "Ab", "b" * 65])
def test_invalid_team_slugs_raise(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_team_slug(value)


@pytest.mark.parametrize("value", ["0.0.1", "1.2.3", "1.0.0-rc.1", "1.0.0+build.5"])
def test_valid_versions_pass(value: str) -> None:
    assert validate_version(value) == value


@pytest.mark.parametrize("value", ["1", "1.2", "v1.2.3", "1.2.3.4", "01.2.3", "^1.2.3", ""])
def test_invalid_versions_raise(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_version(value)
