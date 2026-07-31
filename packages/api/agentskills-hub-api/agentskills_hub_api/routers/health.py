"""Liveness. Unauthenticated by design: a probe must not need a credential."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agentskills_hub_api import __version__

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=Health, summary="Liveness probe")
async def health() -> Health:
    return Health(status="ok", version=__version__)
