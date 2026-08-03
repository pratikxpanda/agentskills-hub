"""Application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentskills_hub_api import __version__
from agentskills_hub_api.errors import ErrorResponse, register_error_handlers
from agentskills_hub_api.routers import catalog, health, publish, subscriptions, teams
from agentskills_hub_api.settings import Settings
from agentskills_hub_core import (
    ArchiveLimits,
    FixedWindowLimiter,
    LocalFileSystemSkillStore,
    create_engine,
    create_session_factory,
)

DESCRIPTION = """
Control plane for organizational Agent Skills.

Every request authenticates with a bearer token of the form `ashub_{prefix}_{secret}`. The team is
resolved from the credential; a team segment in a path is compared against it and never used to
select a team.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()
    engine = create_engine(resolved.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="Agent Skills Hub",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse, "description": "Authentication failed."},
            403: {"model": ErrorResponse, "description": "Credential belongs to another team."},
            429: {"model": ErrorResponse, "description": "Too many failed attempts."},
        },
    )
    # State is built here rather than in the lifespan so that the app is usable the moment it is
    # constructed. An async engine opens no connection until one is asked for, so this costs
    # nothing; the lifespan exists to close what this opened.
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.store = LocalFileSystemSkillStore(
        resolved.store_root,
        ArchiveLimits(
            max_archive_bytes=resolved.max_archive_bytes,
            max_total_bytes=resolved.max_total_bytes,
            max_file_bytes=resolved.max_file_bytes,
            max_members=resolved.max_members,
        ),
    )
    app.state.auth_limiter = FixedWindowLimiter(
        resolved.auth_failure_limit, resolved.auth_failure_window_seconds
    )

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(publish.router)
    app.include_router(catalog.router)
    app.include_router(teams.router)
    app.include_router(subscriptions.router)
    return app
