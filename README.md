# Agent Skills Hub

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: design](https://img.shields.io/badge/status-design-orange.svg)](docs/ROADMAP.md)
[![Built on: Agent Skills SDK](https://img.shields.io/badge/built%20on-agentskills--sdk-blue.svg)](https://github.com/pratikxpanda/agentskills-sdk)

> The control plane for [Agent Skills](https://agentskills.io) inside an organization. Publish a
> skill once, govern it centrally, and deliver it to every team's agents over MCP.

> **Status: design and planning.** There is no implementation yet — this repository currently
> holds the design, the roadmap, the milestone specifications, and the architecture decisions.
> Start with [DESIGN.md](docs/DESIGN.md), then the [roadmap](docs/ROADMAP.md).

---

## The problem

Organizations already write down how things should be done — incident runbooks, review standards,
compliance procedures, deployment checklists. As teams build agents, that knowledge gets
re-encoded as prompt text, once per agent, by whoever happened to need it.

The result is familiar:

- The same procedure exists in six system prompts, in five different states of accuracy.
- Nobody can answer *which agents are following the current version of the security baseline.*
- A team that needs an expert procedure it does not own has no way to ask for one, so it guesses.
- When an agent gives a damaging answer, there is no record of where the instruction came from.

The [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk) solves the technical half:
a skill is a portable, open-format unit of expertise, and an agent can load one on demand. It does
not answer who may publish one, who may use it, at what version, or how anyone finds out it
changed.

That is what the Hub is for.

## What the Hub does

| Actor | Gets |
|---|---|
| **Platform team** | Author and publish skills, review what teams are asking for, control who may subscribe to what, deprecate safely, and see where every skill is in use. |
| **Application team** | Browse a catalog of skills their organization already trusts, subscribe at a pinned version, and connect any agent with one URL. Ask for a skill that does not exist yet. |

An application team's entire integration is one MCP endpoint:

```json
{
  "mcpServers": {
    "skills": {
      "url": "https://hub.internal.example.com/mcp/checkout-squad"
    }
  }
}
```

That endpoint serves the union of the team's subscriptions, at the versions the team pinned. No
Hub client library, no SDK install, no framework lock-in — any MCP client works, including
GitHub Copilot in VS Code, Claude Desktop, Microsoft Agent Framework, and LangChain agents.

## Try it

```bash
git clone https://github.com/pratikxpanda/agentskills-hub.git
cd agentskills-hub
docker compose -f deploy/docker-compose.yml up --build
```

One container, no other prerequisites. It migrates, seeds two teams and two skills, and prints
each team's API key and MCP endpoint:

```
  Checkout Squad (checkout-squad)
    MCP endpoint  http://127.0.0.1:8000/mcp/checkout-squad
    API key       ashub_...
```

The UI is on <http://127.0.0.1:8000>. Point an agent at the printed endpoint with the printed key
as a bearer token — [examples/agent/](examples/agent) has one for Microsoft Agent Framework and
one for LangChain. [deploy/README.md](deploy/README.md) covers configuration, persistence, and
what to change before running it anywhere real.

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                      agentskills-hub                        │
│                        control plane                        │
│                                                             │
│    Intake ──▶ Authoring ──▶ Review ──▶ Publish ──▶ Catalog   │
│                                                    │        │
│                                     Subscriptions ─┤        │
│                                     (team ↔ skill  │        │
│                                      @ version)    │        │
└────────────────────────────────────────────────────┼────────┘
                                                     │
                        ┌────────────────────────────▼────────┐
                        │      agentskills-mcp-server         │
                        │             data plane              │
                        │    skills as MCP tools & resources  │
                        │       (already built in the SDK)    │
                        └────────────────────────────┬────────┘
                                                     │
                                        ┌────────────▼────────┐
                                        │  Any MCP client     │
                                        │  or agent framework │
                                        └─────────────────────┘
```

The Hub **composes** the SDK; it never re-implements it. Skill parsing, validation, retrieval, and
MCP exposure all belong to the SDK. Scope, ownership, versioning, entitlement, and audit belong to
the Hub. That boundary is the project's first architecture decision —
[ADR 0001](docs/adr/0001-hub-is-a-control-plane.md) — and everything else follows from it.

A published skill stays portable: Hub metadata never enters `SKILL.md`, and a version directory
copied out of the store works unmodified with a plain filesystem provider.

## Core concepts

| Concept | Summary |
|---|---|
| **Skill** | A `SKILL.md` in the [open format](https://agentskills.io/specification), plus optional references, scripts, and assets. Unchanged from the SDK. |
| **Scope** | `org`, `domain`, or `team` — determines who sees a skill and how strictly it is governed. Governance is graduated: a team's private skill needs validation, an organization-wide one needs review. |
| **Version** | Immutable once published. Subscriptions pin an exact version; there is no `latest` — [ADR 0003](docs/adr/0003-explicit-version-pinning.md). |
| **Subscription** | The explicit binding of a team to a skill at a version. The only thing that changes what an agent sees. |
| **Intake request** | An application team stating a need the catalog does not meet. The Hub's demand signal. |
| **Catalog** | The browsable set of skills visible to a given team: organization + its domains + its own. |
| **Catalog cost** | What a team's subscriptions cost in context, on every turn. Aggregating three scopes into one endpoint is the Hub's value and its bill; it shows the number rather than hiding it. |

See [DESIGN.md](docs/DESIGN.md) for the full model — actors, lifecycle, promotion, data model, and
deployment shapes, and [GLOSSARY.md](docs/GLOSSARY.md) for the precise meaning of each term.

## Planned shape

| Component | Role |
|---|---|
| `agentskills-hub-core` | Domain model, skill store, repositories. No web framework. |
| `agentskills-hub-api` | FastAPI control plane — catalog, publish, subscriptions, intake, approvals. |
| `agentskills-hub-gateway` | Per-team MCP endpoint. Composes a `SkillRegistry` per connection and serves it through `agentskills-mcp-server`. |
| `agentskills-hub-server` | Composition root: the API, the gateway, and the built UI in one process. The only package that knows all three exist. |
| `agentskills-hub-cli` | `publish`, `search`, `subscribe`, `status`, `diff` — and the CI publishing path. |
| `web/` | Catalog, skill detail, subscriptions, publish, and intake UI. |

Storage is SQLite plus a filesystem content store, deliberately: the Hub must run on a laptop, in
a container, or in a customer's cloud without a rewrite. Azure is a documented deployment target,
not a dependency.

### Known limitations

These are decisions, not omissions. Each has a milestone.

| Limitation | Resolved in |
|---|---|
| **No roles.** Authentication proves which team a request belongs to; it does not grant or withhold permissions. Any authenticated team may publish. | v0.4 (Entra ID and RBAC) |
| Failed-authentication rate limiting is per-process, so it only holds for a single instance. | v0.4 |
| Catalog search is a `LIKE` scan over ids, descriptions, and tags. Correct, and linear in catalog size. | v0.3 (search) |
| One environment per team, created automatically and named `default`. | v0.3 |
| Subscription changes are attributed to the API key that made them, not to a person, and are recorded on the row rather than in an append-only log. | v0.2 (audit log), v0.4 (Entra ID) |
| The MCP gateway rebuilds a team's registry on every request, re-reading each subscribed `SKILL.md`. Correct and trivially isolated; linear in subscriptions per request. | v0.3 (caching) |
| SQLite only. | v1.0 (PostgreSQL) |

## Roadmap

| Milestone | Focus |
|---|---|
| **[v0.1 — Walking Skeleton](docs/issues/v0.1.md)** | Publish → catalog → subscribe → per-team MCP endpoint → agent consumes it. One organization, org scope, open subscriptions, API keys. |
| **[v0.2 — Governance & Workflow](docs/issues/v0.2.md)** | Intake requests, approval gates, upgrades and diffs, team self-authoring, CLI, CI publishing, deprecation, audit log, collections. |
| **v0.3 — Scale & Scope** | Domains, promotion, live subscription updates, multi-tenant caching, search, environments, catalog budgets, policy skills, usage telemetry. |
| **v0.4 — Trust & Supply Chain** | Entra ID and RBAC, skill signing, publish-time content policy, required approvers, isolation review. |
| **v0.5 — Insight & Ecosystem** | Adoption dashboard, catalog health, feedback loop, effectiveness signals, external skill sources, bundles, intake integrations. |
| **v1.0 — Production** | PostgreSQL, horizontal scale, API freeze, SLOs, disaster recovery. |

The [roadmap](docs/ROADMAP.md) carries the reasoning, the product principles, the explicit
non-goals, and the [dependency contract with the SDK](docs/ROADMAP.md#what-the-hub-needs-from-the-sdk).

## Documentation

| Document | Contents |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | The model: actors, scopes, lifecycle, subscriptions, intake, data model, deployment. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Principles, themes, milestones, non-goals, and how work is planned. |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Exact meanings — including the four access terms that are easy to confuse. |
| [docs/issues/](docs/issues/) | Full specifications per milestone — problem, proposal, acceptance criteria. |
| [docs/adr/](docs/adr/README.md) | Architecture decisions and their trade-offs. |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Target repository layout and development workflow. |
| [deploy/README.md](deploy/README.md) | Running the Hub: the image, compose, configuration, and Azure. |
| [examples/](examples/README.md) | Seed corpus and the demo agent. |

## Related

- **[Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk)** — the Python SDK this
  project is built on. Six packages covering the core abstractions, filesystem and HTTP providers,
  LangChain and Microsoft Agent Framework integrations, and an MCP server.
- **[agentskills.io](https://agentskills.io)** — the open format specification.

## Contributing

The most useful contribution right now is disagreement with the design. Open a
[GitHub Discussion](https://github.com/pratikxpanda/agentskills-hub/discussions) or an issue
against a specific section of [DESIGN.md](docs/DESIGN.md) or an
[ADR](docs/adr/). See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
