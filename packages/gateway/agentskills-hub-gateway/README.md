# agentskills-hub-gateway

The MCP endpoint of the [Agent Skills Hub](https://github.com/pratikxpanda/agentskills-hub). One
multi-tenant ASGI application, not one server process per team: the team is resolved from the
presented credential, and the path segment is only a label.

This package defines no MCP tools of its own. It composes `agentskills-mcp-server` from the SDK.
See [ADR 0001](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0001-hub-is-a-control-plane.md)
and [ADR 0004](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0004-multi-tenant-mcp-gateway.md).

**Status:** scaffolding. No endpoint yet.
