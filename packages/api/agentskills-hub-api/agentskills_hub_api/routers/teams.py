"""Team identity.

The only endpoint here reads the caller's own team. It exists so the path-segment rule has
somewhere to live before the subscription endpoints arrive, and so a client can confirm which team
a token belongs to without being told what any other team's tokens do.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agentskills_hub_api.dependencies import TeamScoped

router = APIRouter(prefix="/api/teams", tags=["teams"])


class TeamIdentity(BaseModel):
    team_id: uuid.UUID
    slug: str
    environment_id: uuid.UUID = Field(
        description="The environment this credential resolves to. One per team in v0.1."
    )


@router.get(
    "/{team}",
    response_model=TeamIdentity,
    summary="The team the credential belongs to",
)
async def read_team(principal: TeamScoped) -> TeamIdentity:
    return TeamIdentity(
        team_id=principal.team_id,
        slug=principal.team_slug,
        environment_id=principal.environment_id,
    )
