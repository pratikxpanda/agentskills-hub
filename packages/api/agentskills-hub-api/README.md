# agentskills-hub-api

The FastAPI application behind the [Agent Skills Hub](https://github.com/pratikxpanda/agentskills-hub):
catalog, publishing, subscriptions, and authentication.

Every endpoint that takes a team segment resolves the team from the credential, never from the URL
path. See [ADR 0004](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0004-multi-tenant-mcp-gateway.md).

**Status:** scaffolding. No endpoints yet.
