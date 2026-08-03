"""Request-scoped dependencies.

The authentication dependency is the only place a request becomes a team. Everything downstream
takes the team from the returned principal.

Session and engine types come from `agentskills_hub_core`, not from SQLAlchemy: an import contract
says this layer never depends on the ORM directly, and annotations are imports.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentskills_hub_api.errors import ApiError
from agentskills_hub_api.settings import Settings
from agentskills_hub_core import (
    ApiKeyRepository,
    DatabaseEngine,
    DatabaseSession,
    FixedWindowLimiter,
    LocalFileSystemSkillStore,
    SessionFactory,
    TeamPrincipal,
    authenticate,
    session_scope,
)

_logger = logging.getLogger(__name__)

# auto_error=False so a missing header produces this module's error shape rather than FastAPI's.
_bearer = HTTPBearer(auto_error=False, description="`ashub_{prefix}_{secret}`")

UNAUTHENTICATED = "Authentication failed."


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> DatabaseEngine:
    engine: DatabaseEngine = request.app.state.engine
    return engine


def get_session_factory(request: Request) -> SessionFactory:
    factory: SessionFactory = request.app.state.session_factory
    return factory


def get_store(request: Request) -> LocalFileSystemSkillStore:
    store: LocalFileSystemSkillStore = request.app.state.store
    return store


def get_limiter(request: Request) -> FixedWindowLimiter:
    limiter: FixedWindowLimiter = request.app.state.auth_limiter
    return limiter


async def get_session(
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> AsyncIterator[DatabaseSession]:
    async with session_scope(factory) as session:
        yield session


Session = Annotated[DatabaseSession, Depends(get_session)]
Store = Annotated[LocalFileSystemSkillStore, Depends(get_store)]


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[DatabaseSession, Depends(get_session)],
    limiter: Annotated[FixedWindowLimiter, Depends(get_limiter)],
) -> TeamPrincipal:
    address = _client_key(request)
    token = credentials.credentials if credentials else ""

    if limiter.is_blocked(address):
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            "Too many failed authentication attempts.",
        )

    principal = await authenticate(session, token) if token else None
    if principal is None:
        # No prefix in the message and no token in the log: an unknown prefix and a wrong secret
        # are indistinguishable from outside.
        limiter.record_failure(address)
        _logger.warning("authentication failed from %s", address)
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "unauthenticated", UNAUTHENTICATED)

    limiter.clear(address)
    # Joins the transaction the request already has, and only when the recorded time is stale, so
    # almost every authenticated request still performs no write. A BackgroundTask cannot be used:
    # FastAPI runs background tasks *before* yield-dependency teardown, so this session's write
    # transaction would still be open and a second connection would deadlock against it.
    await ApiKeyRepository(session).touch(principal.api_key_id)
    return principal


Principal = Annotated[TeamPrincipal, Depends(require_principal)]


def require_team_match(team: str, principal: Principal) -> TeamPrincipal:
    """Compare a URL's team segment with the authenticated principal.

    The segment exists for readability and cache keys. Authorisation comes from the credential, so
    a mismatch is a refusal rather than a lookup.
    """
    if team != principal.team_slug:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "team_mismatch",
            "The credential does not belong to this team.",
        )
    return principal


TeamScoped = Annotated[TeamPrincipal, Depends(require_team_match)]
