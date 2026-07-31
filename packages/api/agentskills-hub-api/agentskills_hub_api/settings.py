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
    max_archive_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024
    max_members: int = 2000

    @classmethod
    def from_env(cls) -> Settings:
        from agentskills_hub_core import DEFAULT_DATABASE_URL

        defaults = cls(database_url="", store_root="")
        return cls(
            database_url=os.environ.get("HUB_DATABASE_URL", DEFAULT_DATABASE_URL),
            store_root=os.environ.get("HUB_STORE_ROOT", DEFAULT_STORE_ROOT),
            auth_failure_limit=_int("HUB_AUTH_FAILURE_LIMIT", defaults.auth_failure_limit),
            auth_failure_window_seconds=float(
                os.environ.get(
                    "HUB_AUTH_FAILURE_WINDOW_SECONDS", defaults.auth_failure_window_seconds
                )
            ),
            max_archive_bytes=_int("HUB_MAX_ARCHIVE_BYTES", defaults.max_archive_bytes),
            max_total_bytes=_int("HUB_MAX_TOTAL_BYTES", defaults.max_total_bytes),
            max_file_bytes=_int("HUB_MAX_FILE_BYTES", defaults.max_file_bytes),
            max_members=_int("HUB_MAX_MEMBERS", defaults.max_members),
        )


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))
