"""Resolving a bearer token to the team it belongs to.

This is the single control that keeps one team out of another's instruction set in v0.1, so it
resolves the team from the credential and nothing else. Handlers take the team from the principal;
a team segment in a URL is for readability and cache keys, never for authorisation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from agentskills_hub_core.models import ApiKey, Team
from agentskills_hub_core.repositories import ApiKeyRepository
from agentskills_hub_core.security import split_token, verify_secret


@dataclass(frozen=True)
class TeamPrincipal:
    team_id: uuid.UUID
    team_slug: str
    environment_id: uuid.UUID
    api_key_id: uuid.UUID
    api_key_prefix: str


async def authenticate(session: AsyncSession, token: str) -> TeamPrincipal | None:
    """Resolve a bearer token, or `None`. Callers must not distinguish the reasons for `None`."""
    parsed = split_token(token)
    if parsed is None:
        verify_secret(None, token)
        return None

    prefix, secret = parsed
    key: ApiKey | None = await ApiKeyRepository(session).get_by_prefix(prefix)
    if not verify_secret(key.key_hash if key else None, secret):
        return None
    if key is None or key.revoked_at is not None:
        return None

    team = await session.get(Team, key.team_id)
    if team is None:
        return None

    return TeamPrincipal(
        team_id=team.id,
        team_slug=team.slug,
        environment_id=key.environment_id,
        api_key_id=key.id,
        api_key_prefix=key.prefix,
    )
