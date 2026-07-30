# Agent Skills Hub — Design

> Built on the [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk).

## Overview

Agent Skills Hub is a management and governance layer that enables **platform teams** to author, publish, and manage skills sourced from anywhere, and **application teams** to discover, subscribe to, and consume those skills via standard MCP endpoints.

The Hub sits above the existing SDK, which provides the building blocks — skill format, providers, registry, and MCP server. The Hub adds workflow, access control, catalog browsing, and team-scoped skill delivery.

```
┌─────────────────────────────────────────────────────────────┐
│                      agentskills-hub                        │
│                   (management / control plane)              │
│                                                             │
│  ┌───────────┐   ┌────────────┐   ┌───────────────────┐    │
│  │  Intake    │   │   Skill    │   │   Subscription    │    │
│  │  Requests  │──▶│  Lifecycle │──▶│   Management      │    │
│  │ (app team) │   │ (platform) │   │  (app ↔ skill)    │    │
│  └───────────┘   └────────────┘   └────────┬──────────┘    │
│                                             │               │
│                                   ┌─────────▼──────────┐    │
│                                   │  MCP Server Config  │    │
│                                   │  Generation         │    │
│                                   └─────────┬──────────┘    │
└─────────────────────────────────────────────┼───────────────┘
                                              │
                     ┌────────────────────────▼───────────────────────┐
                     │            agentskills-mcp-server              │
                     │               (data plane)                     │
                     │                                                │
                     │   Skills surfaced as MCP tools & resources     │
                     │   Already built in the SDK                     │
                     └────────────────────────────────────────────────┘
                                              │
                                   ┌──────────▼──────────┐
                                   │   Application Agent  │
                                   │   (any MCP client)   │
                                   └─────────────────────┘
```

### Key Principle

The Hub is a **consumer of the SDK, not a replacement**. `agentskills-mcp-server` is the data plane. The Hub is the control plane. Application teams connect their agents to MCP endpoints — they never interact with the SDK directly.

---

## Actors

| Actor | Role | Primary Actions |
|---|---|---|
| **Platform team** | Governs shared/domain skills | Author skills, review intake requests, manage catalog, approve subscriptions |
| **Domain lead** | Governs domain-scoped skills | Author domain skills, peer review, manage domain catalog |
| **Application team** | Consumes skills via agents | Browse catalog, file intake requests, subscribe, connect agents |
| **Hub admin** | Operates the Hub | Manage orgs, teams, domains, global policies |

These are **roles, not database rows**. The Hub is not an identity provider
([non-goal](./ROADMAP.md#explicit-non-goals)), so it federates identity rather than owning it, and
it does so late:

| Milestone | Principal the Hub authenticates | What a role means |
|---|---|---|
| v0.1 | A **team**, via a hashed API key | Nothing is enforced per person; the team is the unit of authorization |
| v0.4 | A **user**, via Entra ID / OIDC, or a machine token | Roles become real and are enforced by RBAC |

Everywhere this document says *principal* — `published_by`, `assignee`, audit `actor` — it means a
team in v0.1 and a user or machine identity from v0.4. That indirection exists so the schema does
not need rewriting when identity arrives.

---

## Core Concepts

### Skills

A skill is a self-contained unit of expertise authored in the [SKILL.md format](https://agentskills.io). Skills consist of frontmatter metadata, a markdown body with instructions, and optional resources (references, scripts, assets).

The Hub adds management metadata on top of the SDK's skill format. It is split deliberately:
properties of the *skill* change over time; properties of a *version* are fixed at publish.

```yaml
# On the skill — mutable, describes the skill as a whole
scope: org | domain | team
owner: team-reference
visibility: listed | unlisted
subscription_model: open | approval-required
lifecycle: active | deprecated | archived

# On each version — recorded at publish
version: semver
status: draft | review | published | deprecated | archived
content_digest: sha256:…
published_at: timestamp
published_by: principal reference
```

None of this is written into `SKILL.md`. A skill exported from the Hub is a plain SDK skill that
works unmodified with a filesystem provider — see
[ADR 0001](./adr/0001-hub-is-a-control-plane.md).

#### Three independent axes

`scope`, `visibility`, and `subscription_model` are easily confused, because all three sound like
access control. They answer different questions and are evaluated in that order:

| Axis | Question | Values |
|---|---|---|
| **Scope** | *May this team see the skill at all?* | `org` — every team; `domain` — teams in the owning domain; `team` — the owning team only |
| **Visibility** | *Does it appear when they browse?* | `listed` — shown in catalog and search; `unlisted` — reachable only by exact ID or direct link |
| **Subscription model** | *Can they subscribe without asking?* | `open` — immediately; `approval-required` — the owner decides |

`unlisted` is for skills that are in scope but noisy or situational: a runbook for one quarterly
process, or a skill being trialled with two teams before it is announced. It is **not** a security
boundary — scope is. A skill that must not reach a team is out of that team's scope, and no
visibility setting substitutes for that.

### Skill Scopes

Skills are organized into three scopes that control visibility and governance:

```
┌─────────────────────────────────────────────┐
│              Organization-wide              │
│  (shared across all teams)                  │
│                                             │
│  incident-response, security-baseline,      │
│  code-review-standards                      │
├─────────────────────────────────────────────┤
│         Domain (cross-team)                 │
│                                             │
│  ┌─────────────┐   ┌─────────────┐         │
│  │  Payments    │   │  Data/ML    │         │
│  │  pci-compliance│ │  ml-ops     │         │
│  │  gdpr-checks │   │  data-pipeline│       │
│  └─────────────┘   └─────────────┘         │
├─────────────────────────────────────────────┤
│           Team (private)                    │
│                                             │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │
│  │Team A│ │Team B│ │Team C│ │Team D│      │
│  │deploy│ │cart- │ │fraud-│ │search│      │
│  │-rules│ │logic │ │rules │ │-rank │      │
│  └──────┘ └──────┘ └──────┘ └──────┘      │
└─────────────────────────────────────────────┘
```

| Scope | Visible To | Managed By | Governance |
|---|---|---|---|
| **Organization** | All teams | Platform team | Strict — review, validation, versioning |
| **Domain** | Teams in that domain | Domain lead / guild | Moderate — peer review |
| **Team** | Only that team | The team itself | Light — automated validation only |

### Skill Lifecycle

The lifecycle runs at two levels. A **version** moves through publication states. The **skill** has
a coarser state that applies to all of its versions at once.

```
Version:  Draft ──▶ Review ──▶ Published ──▶ Deprecated ──▶ Archived
                                   │
                                   └──▶ supersedes the previous Published version

Skill:    Active ────────────────────────────▶ Deprecated ──▶ Archived
                    │
                    └──▶ Promoted (scope change — see below)
```

| Version state | Meaning |
|---|---|
| **Draft** | The author is still working. Not in the catalog, never served. |
| **Review** | Submitted for approval. Visible to reviewers only. Organization scope requires this step; team scope skips it (principle 3). |
| **Published** | In the catalog and subscribable. |
| **Deprecated** | Still served to existing subscribers, flagged with migration guidance, closed to new subscriptions. |
| **Archived** | Removed from the catalog and from every MCP endpoint. Content is retained for audit and never served again. |

| Skill state | Meaning |
|---|---|
| **Active** | Has at least one published version. |
| **Deprecated** | The skill as a whole is going away; every version inherits the notice. |
| **Archived** | Withdrawn entirely. Subscriptions terminate and the ID is retired, never reused. |

**A published version's content is immutable; its status is not.** Publishing `2.1.0` writes bytes
that will never change — the guarantee that [ADR 0002](./adr/0002-versioned-filesystem-skill-store.md)
and [ADR 0003](./adr/0003-explicit-version-pinning.md) both depend on. Later deprecating or
archiving `2.1.0` changes Hub metadata stored *beside* that content. The two statements only look
contradictory while the distinction is left implicit, which is why it is stated here.

States arrive across milestones, but the columns exist from the first migration so that adding one
is never a data migration:

| State | Available from |
|---|---|
| `Published` | v0.1 — publishing is direct and immediate |
| `Deprecated`, `Archived` | v0.2, with sunset periods and subscriber notification |
| `Draft`, `Review` | v0.4, with the review workflow and required approvers |

### Subscriptions

A subscription binds a team to a skill at a specific version. It is the mechanism that determines what appears in a team's MCP endpoint.

```
Subscription:
  team: checkout-squad
  skill: incident-response
  version: 2.1.0           # pinned
  scope: org
  status: active
```

Subscription models per skill:

| Model | Flow |
|---|---|
| **Open** | Subscribe immediately — no approval needed |
| **Approval-required** | Subscribe triggers approval request to skill owner |

#### Environments

A team holds one subscription set per environment, and each environment has its own MCP endpoint:

```
checkout-squad / production   incident-response 2.1.0
checkout-squad / staging      incident-response 3.0.0
```

This is the answer to the obvious objection to [explicit pinning](./adr/0003-explicit-version-pinning.md)
— that upgrading is otherwise a leap of faith. A team moves the pin in `staging`, points its
non-production agents there, observes the difference, then moves `production`. Without
environments, "test before you upgrade" has no mechanism behind it and the diff view is the only
evidence a team ever gets.

Every team has a `default` environment. Additional environments arrive in v0.3; until then the
field exists and holds one value.

### Collections

A collection is a named, curated set of skills at specific versions that a team subscribes to in
one action:

```
Collection: sre-starter-pack   (owner: platform-team)
  incident-response      2.1.0
  postmortem-writing     1.4.0
  oncall-escalation      1.0.2
```

Subscribing to a collection creates the individual subscriptions it names. Collections are a
**publishing convenience, not a delivery primitive** — the subscriptions they create are ordinary,
independently pinned, and independently removable. Updating a collection notifies subscribed teams
that a newer set exists; it does not move anyone's pins, so principle 4 holds unchanged.

Collections exist because a team's first day in the catalog is otherwise forty decisions it is not
yet equipped to make, and the default response to forty decisions is to make none. Arrives in v0.2.

### Intake Requests

When an application team needs a skill that doesn't exist, they file an intake request:

```
Intake Request:
  requester: checkout-squad
  title: "PCI compliance checks for payment flows"
  description: "We need our agents to follow PCI-DSS..."
  suggested_scope: domain (payments)
  priority: high
  status: submitted → triaged → in-progress → published
  resolved_skill: pci-compliance (once published)
```

This is a **service catalog** pattern — application teams express needs, platform teams fulfill them.

### Catalog

The catalog is the Hub's browsable index of all published skills visible to a given team:

| Viewer | Sees |
|---|---|
| App team | All org skills + their domain skills + their team skills |
| Domain lead | All org skills + all skills in their domain(s) |
| Platform team / admin | Everything |

Each catalog entry surfaces:

- Skill name, latest published version, description
- Owner, scope, tags
- Subscription model (open vs. approval-required)
- Subscriber count
- Published date, and last-reviewed date once staleness tracking lands in v0.5
- Approximate context cost of subscribing — see [What the Agent Actually Sees](#what-the-agent-actually-sees)
- Full `SKILL.md` body (view details)

`unlisted` skills never appear in browse or search results for any viewer other than their owner.
They are still reachable at their canonical URL and still subscribable, subject to scope and
subscription model.

### Skill Promotion

Team-scoped skills can be promoted to broader scopes when they prove useful:

```
Team scope ──▶ Domain scope ──▶ Organization scope
```

Promotion changes the scope and ownership of an existing skill record. It does not copy, fork, or
re-publish anything, so version history and content digests carry across untouched.

| Step | Rule |
|---|---|
| Uniqueness check | The skill ID must be free within the target scope. A collision fails the promotion and the author renames first — the Hub never silently resolves an ambiguous ID on a subscriber's behalf. |
| Re-review | The current published version is re-reviewed under the target scope's governance model before it becomes visible more widely. |
| Ownership transfer | Recorded explicitly, with the originating team retained as a contributor for attribution. |
| Existing subscribers | **Untouched.** Their pins already reference immutable content and keep resolving to exactly that content. |

The last row is the one people expect to read the other way round. Migrating subscribers
automatically would change what a team's agents are told without that team acting, which is
precisely what [ADR 0003](./adr/0003-explicit-version-pinning.md) exists to prevent. **Promotion
widens who *may* subscribe; it never subscribes anyone.**

---

## How Consumption Works

### End-to-End Flow

```
App Team                          Hub                        Platform Team
────────                         ────                       ──────────────

  │ Browse catalog ──────────▶  Show org + domain +          │
  │                              team skills                  │
  │                                                           │
  │ Subscribe (open) ────────▶  Grant immediately             │
  │ Subscribe (gated) ───────▶  Request approval ──────────▶ Approve/deny
  │                                                           │
  │ File intake request ─────▶  Track request ─────────────▶ Author skill
  │                                                    ────▶ Publish
  │                              Notify app team              │
  │ Subscribe to new skill ──▶  Add to subscriptions         │
  │                                                           │
  │ Self-author team skill ──▶  Validate + publish            │
  │                              (team scope only)            │
  │                                                           │
  │ Connect agent via MCP ───▶  Serve subscribed skills       │
  │                              (org + domain + team)        │
```

### MCP Endpoint Per Team

Each team gets an MCP endpoint that serves the **union** of their subscribed skills:

```
checkout-squad's MCP endpoint serves:
├── incident-response        (org scope — all teams get this)
├── pci-compliance           (domain scope — payments domain)
└── cart-logic               (team scope — checkout-squad's own)
```

The Hub composes a `SkillRegistry` from the team's subscriptions and runs (or configures) an `agentskills-mcp-server` instance.

### Agent Configuration

From the application team's perspective, consumption is a single MCP connection:

```json
{
  "mcpServers": {
    "skills": {
      "url": "https://hub.internal.co/mcp/checkout-squad"
    }
  }
}
```

The path segment is a human-readable label. The team and environment actually served are resolved
from the credential presented on the connection, never from the URL — see
[ADR 0004](./adr/0004-multi-tenant-mcp-gateway.md). A staging key on the same URL yields the staging
subscription set.

Any MCP-compatible client works — Claude Desktop, VS Code, LangChain, Agent Framework, custom agents.

### What the Agent Actually Sees

Every subscribed skill costs context on **every turn**, whether or not it is used. The SDK injects a
catalog — one short entry per skill — and loads a body only when the agent asks for it. That is what
makes progressive disclosure work, and it is also what makes the Hub's aggregation a cost centre:
the Hub is the component that hands a team the union of three scopes.

| Subscriptions | Approximate catalog cost, per turn |
|---|---|
| 5 | ~200 tokens |
| 20 | ~800 tokens |
| 50 | ~2,000 tokens |
| 150 | ~6,000 tokens |

The figures are indicative — roughly 40 tokens per entry — but the shape is the point, and it is
linear and permanent. The Hub is also the only component that can see a team's *total* subscription
set, so it is the only component that can be held accountable for that number. Three rules follow:

1. **Catalog cost is a displayed number, not an implementation detail.** The catalog shows what an
   individual skill adds; the subscriptions page shows the running total per environment. A team
   should never first learn its prompt budget from a bill.
2. **Budgets are enforced at subscribe time, and loudly.** A team may set a per-environment token
   budget. Exceeding it is refused when subscribing, naming the total and the offender — never
   silently truncated at serve time. Silent truncation means an agent's instructions differ between
   turns for reasons nobody can observe, which is the worst failure mode in the system.
3. **Filtering is allowed; hiding is not.** Once the SDK supports catalog filtering and semantic
   selection, the gateway may narrow what it advertises for a given turn. The team's catalog page
   still shows the full subscribed set, and telemetry records what was actually advertised.

The corollary is uncomfortable and worth stating: **subscription count is not an adoption metric to
maximise.** A team subscribed to everything has the same problem as a team subscribed to nothing,
arrived at more expensively. Curation is the product.

---

## Data Model

```
Organization
 └── Domain (0..n)
      └── Team (1..n)
           └── Environment (1..n)          # "default" only until v0.3

Principal                                    # see Actors — a team in v0.1, a user from v0.4
 ├── kind: team-key | user | machine
 └── roles: string[]                        # enforced from v0.4 (RBAC)

Skill
 ├── id: string (unique within scope + owner)
 ├── scope: org | domain | team
 ├── owner: reference (team or domain)
 ├── visibility: listed | unlisted
 ├── subscription_model: open | approval-required
 ├── lifecycle: active | deprecated | archived
 ├── tags: string[]
 └── versions[]
      ├── version: semver
      ├── status: draft | review | published | deprecated | archived
      ├── content: SKILL.md + resources (immutable once published)
      ├── content_digest: sha256 (of the published tree)
      ├── catalog_tokens: int (cost of this version's catalog entry)
      ├── published_at: timestamp
      └── published_by: principal reference

Collection                                   # v0.2
 ├── id, title, owner: reference
 └── members[]: (skill reference, version)

Subscription
 ├── team: reference
 ├── environment: reference (default "default")
 ├── skill: reference
 ├── version: semver (pinned — no ranges, no "latest")
 ├── origin: manual | collection | policy   # why this skill is on the endpoint
 ├── status: active | pending-approval | revoked
 └── subscribed_at: timestamp

IntakeRequest
 ├── requester: team reference
 ├── title: string
 ├── description: string
 ├── suggested_scope: org | domain | team
 ├── priority: low | medium | high
 ├── status: submitted | triaged | in-progress | published | declined
 ├── assignee: principal reference (nullable)
 └── resolved_skill: skill reference (nullable)

AuditEvent                                   # v0.2, append-only
 ├── at: timestamp
 ├── actor: principal reference
 ├── action: published | approved | subscribed | deprecated | promoted | …
 ├── subject: skill / version / subscription reference
 └── detail: json (identifiers and digests — never bodies or secrets)
```

`Subscription.origin` is what lets a team answer "why is this skill on my endpoint?" without
guessing — it distinguishes a deliberate subscription from one created by a collection or by
organization policy ([ADR 0005](./adr/0005-default-and-mandatory-skills.md)).

---

## Hub Components

| Component | Responsibility |
|---|---|
| **Hub API** | REST API for all Hub operations — catalog, subscriptions, intake, skill management |
| **Skill Store** | Versioned skill content storage, backed by the SDK's existing providers (filesystem, blob storage, Git) |
| **Subscription Manager** | Team ↔ skill entitlements, version pinning, approval workflows |
| **MCP Gateway** | Per-team MCP endpoints — builds registry from subscriptions, delegates to `agentskills-mcp-server` |
| **Intake Tracker** | Request lifecycle, assignment, status tracking |
| **Admin UI** | Web interface for all actors — browse catalog, manage skills, review requests, configure teams |
| **CLI** | Developer-facing commands — publish skills, search catalog, manage subscriptions from terminal |

---

## Deployment Models

### Hosted (Hub runs MCP endpoints)

```
Hub Service ──manages──▶ MCP Server Pool
                              │
              App agents connect via MCP
```

Simplest for application teams. Hub manages the full stack.

### Self-Hosted (Hub exports a bundle) — v0.5

```
Hub Service ──exports──▶ signed skill bundle + server.json
                              │
              App team runs its own agentskills-mcp-server
```

For air-gapped or high-security environments. This model requires something the hosted one does
not, and the requirement is easy to miss: **a generated configuration file is useless on its own**,
because the app team's network cannot reach the Hub's content store. Self-hosting therefore depends
on skill bundles — a portable archive of a subscription set at its pinned versions, exported by the
Hub and verifiable independently of it. That is why bundles are scheduled ahead of this deployment
model rather than beside it.

What the app team accepts in exchange: subscription and version changes take effect only when a new
bundle is pulled, and usage telemetry is unavailable unless they choose to ship it back.

### Hybrid

Hub manages catalog and subscriptions centrally. MCP servers run in the application team's
infrastructure but pull configuration — and content, over an authenticated HTTP provider — from the
Hub API. This keeps live subscription updates and telemetry while placing the data plane inside the
team's network boundary. It requires connectivity to the Hub, so it is not an air-gap story.

---

## SDK Impact

The Hub composes the SDK and re-implements none of it — see
[ADR 0001](./adr/0001-hub-is-a-control-plane.md). Several Hub capabilities therefore depend on SDK
work, tracked as a dependency contract in the
[roadmap](./ROADMAP.md#what-the-hub-needs-from-the-sdk) and as issues in the SDK repository.

| Change | Package | Why |
|---|---|---|
| `version` field in frontmatter | `agentskills-core` | Enable version pinning in subscriptions |
| Provider content caching | providers | One gateway process serving many teams from one store |
| Resource discovery | `agentskills-core` + providers | Publish-time inventory and catalog resource browsing |
| Catalog filtering & token budget | `agentskills-core` | Bounded prompt cost for teams with large subscription sets |
| Dynamic registry updates | `agentskills-core` | Add/remove skills without restart (long-lived MCP servers) |
| MCP server config hot-reload | `agentskills-mcp-server` | Subscription changes reflected without redeploy |
| Skill integrity & provenance | `agentskills-core` | Publish-time signing and verification |
| Usage telemetry hooks | `agentskills-core` | Adoption analytics from the data plane |

All are backward-compatible additions. A Hub item blocked on one of them ships with documented
interim behaviour rather than a private implementation.

---

## Decisions Made

Questions this document originally left open, and where they were settled. ADRs are immutable —
revisiting one means writing a new ADR that supersedes it.

| Question | Decision | Record |
|---|---|---|
| **Relationship to the SDK** — where does the boundary sit? | The SDK is the data plane; the Hub is the control plane and implements none of it. Hub metadata never enters `SKILL.md`. | [ADR 0001](./adr/0001-hub-is-a-control-plane.md) |
| **Store layout** — how is versioned content addressed? | `{root}/skills/{skill_id}/{version}/{skill_id}/`, so a published version is already a valid SDK provider root. Immutable, atomically committed, digested at publish. | [ADR 0002](./adr/0002-versioned-filesystem-skill-store.md) |
| **Version resolution** — exact pinning, ranges, or `latest`? | Exact pinning only. A floating pin lets anyone who can publish silently rewrite the instructions of every subscribed production agent. The Hub compensates with diffs, notifications, and one-click upgrade. | [ADR 0003](./adr/0003-explicit-version-pinning.md) |
| **MCP gateway topology** — one server per team, per domain, or shared? | One multi-tenant process, team resolved per connection from the authenticated principal, never from the URL. | [ADR 0004](./adr/0004-multi-tenant-mcp-gateway.md) |
| **Organization policy** — may the Hub place a skill on a team's endpoint without that team asking? | Yes, for a narrow, audited, version-pinned policy set. It is the single sanctioned exception to principle 4 and carries explicit obligations. | [ADR 0005](./adr/0005-default-and-mandatory-skills.md) |

---

## Open Questions

1. **Skill dependencies** — Can skills reference other skills? If yes, the Hub needs dependency
   resolution, and pinning becomes transitive. Deliberately unanswered until there is evidence real
   catalogs need it.
2. **Intake integrations** — Native intake UI, or plug into Jira / ServiceNow / Azure Boards?
   Current direction is native first with webhooks, and connectors in v0.5.
3. **Skill authoring** — Git-native (PRs) or Hub-native (built-in editor)? Current direction is
   Git-native via CI publishing in v0.2, with the Hub UI as the path for non-engineers.
4. **Observability** — What usage data flows back to platform teams, and what is the privacy
   boundary when that data describes how individuals' agents behave?
5. **Bundle format** — Air-gapped delivery is decided in principle; the archive format, the
   signature scheme, and whether verification must be possible without contacting the issuing Hub
   are not.
6. **Multi-format** — Only `SKILL.md`, or import adapters for `AGENTS.md`, Copilot instructions,
   and Cursor rules? Depends on the SDK's foreign-format adapter work.
7. **Cost accounting** — Token budgets are model-specific, because tokenisers are. Does the Hub
   report one approximate number, or a figure per model family, and who owns the drift when a
   vendor changes tokenisers?
8. **Ownership decay** — When an owning team is dissolved or reorganised, who inherits its
   published skills? Orphaned organization-scoped skills are the most likely source of stale
   instructions reaching production agents.
9. **Promotion re-review depth** — On promotion, is only the current published version re-reviewed,
   or the whole version history that subscribers may still be pinned to?

