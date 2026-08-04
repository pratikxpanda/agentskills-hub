"""One process: the API, the MCP gateway, and the built UI.

Everything here is assembly. There is no behaviour in this package that the API or the gateway
does not already have on its own, and there must never be -- the moment a decision lives only in
the composed app, running the two edges separately stops being a deployment choice.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from agentskills_hub_api.app import create_app
from agentskills_hub_api.settings import Settings
from agentskills_hub_gateway import GatewaySettings, create_gateway_app

__version__ = "0.1.0"

WEB_ROOT_ENV = "HUB_WEB_ROOT"
DEFAULT_WEB_ROOT = "./web/dist"

# Prefixes the UI must never answer for. Without this, a mistyped API path returns the SPA with a
# 200 and a client reports "unexpected token '<'" instead of the 404 it was given.
RESERVED_PREFIXES = ("api", "mcp")


class _Remounted:
    """Undoes what mounting does to a path.

    The gateway owns the whole `/mcp/{team}` path because standalone it is the whole application.
    Rewriting its routes so that it could be mounted would make the composed shape the real one.

    Starlette has moved the prefix between `path` and `root_path` across versions, so both are
    repaired: the prefix is put back on `path` if it is missing, and taken off `root_path` if it
    is there.
    """

    def __init__(self, app: Any, prefix: str) -> None:
        self._app = app
        self._prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = str(scope.get("path", ""))
            if not path.startswith(self._prefix):
                path = self._prefix + path
            root_path = str(scope.get("root_path", ""))
            if root_path.endswith(self._prefix):
                root_path = root_path[: -len(self._prefix)]
            scope = {**scope, "path": path, "root_path": root_path}
        await self._app(scope, receive, send)


class _Spa(StaticFiles):
    """Serves the built UI, falling back to `index.html` so client-side routes survive a reload."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        # `path` arrives as an OS path, so on Windows its separators are backslashes.
        reserved = path.replace("\\", "/").lstrip("/").split("/", 1)[0] in RESERVED_PREFIXES
        try:
            return await super().get_response(path, scope)
        except HTTPException as missing:
            if reserved or missing.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_server_app(
    settings: Settings | None = None,
    gateway_settings: GatewaySettings | None = None,
    web_root: str | None = None,
) -> FastAPI:
    api = create_app(settings)
    gateway = create_gateway_app(gateway_settings)

    # The API's own lifespan closes its engine; the gateway's never runs once it is mounted, so
    # its state is disposed here instead.
    api_lifespan = api.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with api_lifespan(app):
            try:
                yield
            finally:
                await gateway.state.gateway.dispose()

    api.router.lifespan_context = lifespan

    # After the API's routes, so `/api/...` never reaches the gateway, and before the UI, which
    # answers everything else.
    api.mount("/mcp", _Remounted(gateway, "/mcp"))

    root = Path(web_root or os.environ.get(WEB_ROOT_ENV, DEFAULT_WEB_ROOT))
    if (root / "index.html").is_file():
        api.mount("/", _Spa(directory=root, html=True), name="ui")

    return api


__all__ = [
    "DEFAULT_WEB_ROOT",
    "RESERVED_PREFIXES",
    "WEB_ROOT_ENV",
    "__version__",
    "create_server_app",
]
