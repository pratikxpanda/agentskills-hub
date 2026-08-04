"""The ASGI entry point: `uvicorn agentskills_hub_server.asgi:app`.

Separate from the package's `__init__` so that importing the composition root does not build an
application out of whatever happens to be in the environment.
"""

from __future__ import annotations

from agentskills_hub_server import create_server_app

app = create_server_app()

__all__ = ["app"]
