"""Turning a team's subscriptions into an SDK registry.

This is the whole of the Hub's data plane logic: read the pins, point one SDK provider at each
pinned version's directory, hand the result to the SDK's MCP server. Everything that makes a skill
a skill -- parsing, validation, tool shape -- belongs to the SDK, and an import contract keeps it
that way.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from agentskills_core import SkillRegistry
from agentskills_fs import LocalFileSystemSkillProvider

from agentskills_hub_core import CatalogRepository, DatabaseSession, LocalFileSystemSkillStore

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComposedRegistry:
    """A registry plus the story of what did not make it into one.

    `unavailable` exists so that one unreadable skill costs that skill rather than the session. A
    team whose fifth skill is missing from the store still gets the other four.
    """

    registry: SkillRegistry
    skills: list[str]
    unavailable: list[str]


async def compose(
    session: DatabaseSession,
    store: LocalFileSystemSkillStore,
    environment_id: uuid.UUID,
) -> ComposedRegistry:
    subscriptions = await CatalogRepository(session).list_subscriptions(environment_id)

    registry = SkillRegistry()
    composed: list[str] = []
    unavailable: list[str] = []
    for pin in subscriptions:
        if not store.exists(pin.skill_id, pin.version):
            unavailable.append(f"{pin.skill_id}@{pin.version}")
            _logger.warning("no stored content for %s %s", pin.skill_id, pin.version)
            continue
        try:
            provider = LocalFileSystemSkillProvider(store.version_root(pin.skill_id, pin.version))
            await registry.register(pin.skill_id, provider)
        except (OSError, ValueError):
            # The SDK rejects what it will not serve. Refusing the whole session over it would
            # turn one team's bad publish into every skill that team subscribes to.
            unavailable.append(f"{pin.skill_id}@{pin.version}")
            _logger.warning("could not register %s %s", pin.skill_id, pin.version, exc_info=True)
            continue
        composed.append(pin.skill_id)

    return ComposedRegistry(registry=registry, skills=composed, unavailable=unavailable)


__all__ = ["ComposedRegistry", "compose"]
