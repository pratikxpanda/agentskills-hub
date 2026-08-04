# agentskills-hub-server

The composition root. It is the only package allowed to know that the API, the MCP gateway, and
the UI end up in one process, and an import contract forbids anything else from importing it.

That restriction is the point. The API must not learn that a gateway exists and the gateway must
not learn that an API does, or "run them separately" stops being a deployment decision and becomes
a rewrite. Somewhere, something has to put them together; this is that place, and it is small
enough to read in one sitting.

```python
from agentskills_hub_server import create_server_app

app = create_server_app()
```

```bash
uvicorn agentskills_hub_server.asgi:app --host 0.0.0.0 --port 8000
```

Configuration is entirely environment-driven and is documented in
[docs/DEVELOPMENT.md](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/DEVELOPMENT.md).
The one variable this package adds is `HUB_WEB_ROOT`: point it at the built UI and the same origin
serves the SPA, which is why the Hub ships no CORS middleware.
