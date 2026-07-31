"""Runtime configuration.

Read from the environment once at startup. Paths are held as strings so that this layer never
imports `pathlib` -- filesystem access belongs to `agentskills-hub-core`, and the import contract
says so.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_STORE_ROOT = "./store"


@dataclass(frozen=True)
class Settings:
    database_url: str
    store_root: str
    auth_failure_limit: int = 10
    auth_failure_window_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> Settings:
        from agentskills_hub_core import DEFAULT_DATABASE_URL

        return cls(
            database_url=os.environ.get("HUB_DATABASE_URL", DEFAULT_DATABASE_URL),
            store_root=os.environ.get("HUB_STORE_ROOT", DEFAULT_STORE_ROOT),
            auth_failure_limit=int(os.environ.get("HUB_AUTH_FAILURE_LIMIT", "10")),
            auth_failure_window_seconds=float(
                os.environ.get("HUB_AUTH_FAILURE_WINDOW_SECONDS", "60")
            ),
        )
