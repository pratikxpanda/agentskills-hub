"""The per-team MCP endpoint.

One multi-tenant ASGI app rather than a process per team (ADR 0004). A connection authenticates,
resolves to exactly one team, and is served a registry composed from that team's own pins.

The registry -- and the MCP server around it -- is built per request and thrown away. That is the
v0.1 trade named in the milestone: correct and trivially isolated, at the cost of re-reading each
subscribed `SKILL.md`. Caching is v0.3 and is gated on the SDK's provider cache, because a cache
here would be a second implementation of one the SDK is already going to ship.

Building per request is only viable because the transport is stateless: an MCP session that spans
requests would pin a client to one registry, and then "unsubscribing removes the skill from the
next connection" would stop being true.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from agentskills_core import SkillRegistry
from agentskills_mcp_server import create_mcp_server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from agentskills_hub_core import (
    ApiKeyRepository,
    FixedWindowLimiter,
    LocalFileSystemSkillStore,
    SessionFactory,
    TeamPrincipal,
    authenticate,
    create_engine,
    create_session_factory,
    session_scope,
)
from agentskills_hub_gateway.composition import compose
from agentskills_hub_gateway.settings import GatewaySettings

_logger = logging.getLogger(__name__)

UNAUTHENTICATED = "Authentication failed."

_INSTRUCTIONS = (
    "These skills are the ones this team has explicitly subscribed to, each pinned to an exact "
    "version. Read a skill's body before acting on its subject."
)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    """The API's error shape, by hand.

    The shape is a contract with clients; the module that spells it is not shared, because an
    import contract keeps the two edges independent.
    """
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": []}},
    )


class _RefusalError(Exception):
    def __init__(self, response: JSONResponse) -> None:
        self.response = response


class GatewayState:
    """Everything a request needs, built once."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.engine = create_engine(settings.database_url)
        self.sessions: SessionFactory = create_session_factory(self.engine)
        self.store = LocalFileSystemSkillStore(settings.store_root)
        self.limiter = FixedWindowLimiter(
            settings.auth_failure_limit, settings.auth_failure_window_seconds
        )

    async def dispose(self) -> None:
        await self.engine.dispose()


def _bearer(headers: dict[str, str]) -> str:
    value = headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def _principal(
    state: GatewayState, team: str, headers: dict[str, str], client: str
) -> TeamPrincipal:
    """Authenticate and check the team segment, before anything else happens.

    Composing a registry reads the store; doing that for an unauthenticated caller would let an
    unauthenticated caller cause work.
    """
    if state.limiter.is_blocked(client):
        raise _RefusalError(
            _error(429, "too_many_attempts", "Too many failed authentication attempts.")
        )

    token = _bearer(headers)
    async with session_scope(state.sessions) as session:
        principal = await authenticate(session, token) if token else None
        if principal is None:
            state.limiter.record_failure(client)
            _logger.warning("gateway authentication failed from %s", client)
            raise _RefusalError(_error(401, "unauthenticated", UNAUTHENTICATED))
        state.limiter.clear(client)
        await ApiKeyRepository(session).touch(principal.api_key_id)

    if team != principal.team_slug:
        raise _RefusalError(
            _error(403, "team_mismatch", "The credential does not belong to this team.")
        )
    return principal


class McpEndpoint:
    """A raw ASGI endpoint, so the SDK's streamable HTTP app can be handed the connection whole.

    Starlette only wraps functions in its request/response adapter, so an instance with `__call__`
    reaches the transport unmodified.
    """

    def __init__(self, state: GatewayState) -> None:
        self._state = state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        team = str(request.path_params["team"])
        client = request.client.host if request.client else "unknown"
        try:
            principal = await _principal(self._state, team, dict(request.headers), client)
        except _RefusalError as refusal:
            await refusal.response(scope, receive, send)
            return

        async with session_scope(self._state.sessions) as session:
            composed = await compose(session, self._state.store, principal.environment_id)

        server = _server(self._state.settings, composed.registry)
        app = server.streamable_http_app()
        async with server.session_manager.run():
            # The SDK's app owns the path it was built with; this one is mounted under the team.
            await app({**scope, "path": "/mcp", "root_path": ""}, receive, send)


def _server(settings: GatewaySettings, registry: SkillRegistry) -> Any:
    """Returns the SDK's `FastMCP`, untyped: an import contract keeps `mcp` out of this package,
    and an annotation is an import."""
    server = create_mcp_server(registry, name=settings.server_name, instructions=_INSTRUCTIONS)
    # Set after construction because the SDK's factory does not forward FastMCP settings. Stateless
    # is not a tuning choice here: it is what makes a per-request registry honest.
    server.settings.stateless_http = True
    server.settings.json_response = True
    # Mutated rather than replaced for the same reason: constructing the settings type would mean
    # importing it. Left unset, the transport answers 421 to every hostname that is not loopback.
    # Untyped for that reason too -- naming the optional away would need the type in hand.
    security: Any = server.settings.transport_security
    security.allowed_hosts = list(settings.allowed_hosts)
    security.allowed_origins = list(settings.allowed_origins)
    return server


def _check_endpoint(state: GatewayState) -> Callable[[Request], Awaitable[JSONResponse]]:
    async def check(request: Request) -> JSONResponse:
        team = str(request.path_params["team"])
        client = request.client.host if request.client else "unknown"
        try:
            principal = await _principal(state, team, dict(request.headers), client)
        except _RefusalError as refusal:
            return refusal.response

        async with session_scope(state.sessions) as session:
            composed = await compose(session, state.store, principal.environment_id)

        return JSONResponse(
            {
                "team": principal.team_slug,
                "skill_count": len(composed.skills),
                "skills": composed.skills,
                "unavailable": composed.unavailable,
            }
        )

    return check


def create_gateway_app(settings: GatewaySettings | None = None) -> Starlette:
    state = GatewayState(settings or GatewaySettings.from_env())

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await state.dispose()

    app = Starlette(
        routes=[
            # Before the MCP route: a team can verify its wiring without an agent, and without
            # the answer being an MCP error frame.
            Route("/mcp/{team}/check", endpoint=_check_endpoint(state), methods=["GET"]),
            Route(
                "/mcp/{team}",
                endpoint=McpEndpoint(state),
                methods=["GET", "POST", "DELETE"],
            ),
        ],
        lifespan=lifespan,
    )
    app.state.gateway = state
    return app


__all__ = ["GatewayState", "McpEndpoint", "create_gateway_app"]
