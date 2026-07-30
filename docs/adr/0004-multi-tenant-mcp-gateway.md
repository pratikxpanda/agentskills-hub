# ADR 0004 — One multi-tenant MCP gateway, with the team resolved per connection

**Status:** Accepted
**Date:** 2026-07
**Areas:** `gateway`, `auth`

## Context

Each team gets an MCP endpoint serving the union of its subscriptions. How that endpoint is
realised was left open in [DESIGN.md](../DESIGN.md).

Three topologies were on the table:

1. **One MCP server process per team.** Strongest isolation, and how the SDK's MCP server is
   normally run — a config file, a process.
2. **One process per domain.** Fewer processes, weaker isolation, and a boundary that stops making
   sense the moment a team belongs to two domains.
3. **One multi-tenant process, team resolved per connection.** One thing to deploy and supervise;
   isolation becomes application logic rather than an operating-system boundary.

The workload argues against (1) and (2). A team's endpoint is idle almost all the time and
stateless when active: on connection it needs a registry composed from a database query, and
nothing persists between connections. A process per team is a supervision tree, a port allocation
scheme, a config generation step, and an invalidation path — all to serve a request that costs a
`SELECT` and a few directory reads.

Against (3) is the fact that tenant isolation stops being enforced by the operating system and
starts being enforced by code that has to be right.

## Decision

**One multi-tenant ASGI application. The team is resolved per connection from the authenticated
principal, and a registry is composed for that connection.**

In v0.1 it is mounted alongside the REST API in a single process, because there is nothing to gain
from two. The package boundary (`agentskills-hub-gateway`) is kept separate so it can be deployed
independently once its scaling profile diverges.

Per connection:

1. Authenticate the bearer token and resolve a `TeamPrincipal`.
2. Compare the `{team}` path segment to the principal; `403` on mismatch.
3. Query the team's active subscriptions.
4. Compose a `SkillRegistry`, one SDK provider per subscription
   ([ADR 0002](./0002-versioned-filesystem-skill-store.md)).
5. Serve that registry through `agentskills-mcp-server`.

Isolation rules, treated as the load-bearing part of this decision:

- **Authorisation never comes from the URL.** The team segment exists for readability, logging, and
  cache keys. Authorisation is always the principal. The mismatch check is not defence in depth —
  it is the primary control, and it has a dedicated test module.
- **A registry belongs to one connection.** It is never shared, pooled, or cached across teams.
- **Shared caches are keyed by content, never by team.** When provider caching arrives
  ([SDK v0.3](https://github.com/pratikxpanda/agentskills-sdk/blob/main/docs/ROADMAP.md)), the key
  is `(skill_id, version)` — an immutable coordinate. A cache keyed by anything team-derived is
  where cross-tenant leakage would come from.
- **Errors are sanitised.** A message must not reveal whether a skill exists in another team's
  scope. Unauthorised and non-existent are the same response.
- **Isolation is tested adversarially, not assumed.** Every endpoint with a team segment has a
  cross-tenant test, and v0.4 adds a dedicated isolation review whose findings become tests.

Registries are rebuilt per connection rather than cached. This is correct, trivially isolated, and
adequate while connections are long-lived. Caching and live invalidation are v0.3 work, gated on
dynamic registry mutation in the SDK — until that exists, a cached registry could not be
invalidated on a subscription change anyway, which would trade a small cost for a correctness bug.

## Consequences

**Good**

- One process to build, deploy, supervise, and observe. `docker compose up` is a complete Hub.
- Subscription changes take effect on the next connection with no process management.
- Scales horizontally by adding stateless replicas, since no per-team state is held.
- One code path for authentication and authorisation across REST and MCP.

**Costs**

- Tenant isolation is application logic. A bug leaks another team's private instructions, which is
  this system's worst outcome. Accepted deliberately, with the testing obligations above as the
  price.
- A noisy team can affect others in the shared process. Acceptable at the target scale; per-tenant
  rate limiting is the answer before process separation is.
- Registry rebuild per connection is wasted work at scale. Bounded by connection frequency and
  addressed in v0.3.

## Alternatives considered

- **Process per team.** Rejected: operationally heavy for an idle, stateless workload, and it moves
  the isolation guarantee to the OS at the cost of a config-generation and supervision layer that
  becomes the new source of bugs. Reconsider only for hosted multi-organization deployments where
  isolation must be demonstrable to an auditor rather than argued.
- **Process per domain.** Rejected: inherits the operational cost without a clean isolation
  boundary, and breaks outright for teams in multiple domains.
- **Generate a static `server.json` per team and have teams run their own MCP server.** Retained as
  the *self-hosted deployment model* in DESIGN.md, not as the default. It pushes operations onto
  application teams and makes subscription changes require a redeploy on their side, which defeats
  the point of a control plane.
