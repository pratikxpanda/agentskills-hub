"""Runtime configuration for the gateway.

Separate from the API's settings because an import contract forbids the two edges from depending
on each other. They read the same environment variables, which is what makes running them in one
process a deployment choice rather than a coupling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_STORE_ROOT = "./store"
DEFAULT_SERVER_NAME = "Agent Skills Hub"
# The transport refuses any Host it was not told about, and defaults to loopback only. Kept as the
# SDK's default rather than widened, so a deployment behind a real hostname fails closed and says
# so, instead of quietly accepting a rebound DNS name.
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*")


@dataclass(frozen=True)
class GatewaySettings:
    database_url: str
    store_root: str
    server_name: str = DEFAULT_SERVER_NAME
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    auth_failure_limit: int = 10
    auth_failure_window_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> GatewaySettings:
        from agentskills_hub_core import DEFAULT_DATABASE_URL

        defaults = cls(database_url="", store_root="")
        return cls(
            database_url=os.environ.get("HUB_DATABASE_URL", DEFAULT_DATABASE_URL),
            store_root=os.environ.get("HUB_STORE_ROOT", DEFAULT_STORE_ROOT),
            server_name=os.environ.get("HUB_MCP_SERVER_NAME", defaults.server_name),
            allowed_hosts=_csv("HUB_ALLOWED_HOSTS", defaults.allowed_hosts),
            allowed_origins=_csv("HUB_ALLOWED_ORIGINS", defaults.allowed_origins),
            auth_failure_limit=int(
                os.environ.get("HUB_AUTH_FAILURE_LIMIT", defaults.auth_failure_limit)
            ),
            auth_failure_window_seconds=float(
                os.environ.get(
                    "HUB_AUTH_FAILURE_WINDOW_SECONDS", defaults.auth_failure_window_seconds
                )
            ),
        )


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


__all__ = [
    "DEFAULT_ALLOWED_HOSTS",
    "DEFAULT_ALLOWED_ORIGINS",
    "DEFAULT_SERVER_NAME",
    "DEFAULT_STORE_ROOT",
    "GatewaySettings",
]
