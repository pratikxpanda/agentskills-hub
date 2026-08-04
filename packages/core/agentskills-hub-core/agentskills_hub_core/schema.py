"""Applying migrations without needing a checkout on disk.

The runtime image installs packages rather than the repository, so `alembic.ini`'s repo-relative
`script_location` means nothing to it. The migration scripts ship inside this package, so the
configuration that finds them ships here too.

The test suite deliberately does *not* use this: it drives Alembic through the repository's own
`alembic.ini`, because "the file a developer edits still works" is a separate claim.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from agentskills_hub_core.database import DEFAULT_DATABASE_URL

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str | None = None) -> None:
    """Bring a database to the current schema.

    Running this against a database already at head is a no-op, which is what lets a container
    start it unconditionally.
    """
    url = database_url or os.environ.get("HUB_DATABASE_URL") or DEFAULT_DATABASE_URL
    command.upgrade(alembic_config(url), "head")


if __name__ == "__main__":  # pragma: no cover - exercised by the container entrypoint
    upgrade_to_head()
