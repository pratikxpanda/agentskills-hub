# Agent Skills Hub — Roadmap

> Public roadmap for [Agent Skills Hub](../README.md). Themes and ordering, not dates.

This document describes **what we intend to build and why**. It is intentionally coarse-grained:
detailed scoping, discussion, and progress tracking live in
[GitHub Issues](https://github.com/pratikxpanda/agentskills-hub/issues), grouped by milestone.

Written-up specifications for the items below — problem, approach, open questions, acceptance
criteria — live in [docs/issues/](./issues/), one file per milestone.

Read [DESIGN.md](./DESIGN.md) first. It defines the actors, scopes, lifecycle, and data model
that every item below assumes.

## Product Principles

These constrain every item below. If a proposal conflicts with one of these, it needs an
explicit design doc arguing the trade-off.

1. **The SDK is the data plane; the Hub never re-implements it.** Parsing, validation, retrieval,
   and MCP exposure belong to [`agentskills-core`](https://github.com/pratikxpanda/agentskills-sdk)
   and `agentskills-mcp-server`. When the Hub needs behaviour the SDK lacks, the fix is an SDK
   issue, not a private fork inside the Hub.
2. **MCP is the only consumption contract.** An application team's integration cost is one URL and
   one token — no Hub client library, no SDK install, no framework lock-in. A capability that
   cannot be delivered through MCP tools and resources belongs in the control plane, not in the
   agent.
3. **Governance is graduated, not uniform.** Team-scoped skills get automated validation only;
   organization-scoped skills get review. Forcing every skill through the strictest path kills
   authoring. Forcing none through it kills trust.
4. **A team's prompt surface changes only when the team changes it.** Subscriptions are explicit
   and version-pinned. A skill reaches an agent because someone subscribed, and moves to a new
   version because someone upgraded. Silent global rollout is a bug. The single sanctioned
   exception is organization policy — mandatory baseline skills — which is why it needs
   [its own decision record](./adr/0005-default-and-mandatory-skills.md) and its own obligations
   rather than a quiet feature flag.
5. **Skills are untrusted content, and the Hub is where trust is decided.** The Hub is the only
   layer holding provenance, review history, and policy context. Integrity, scanning, and
   attribution are product features here, not documentation footnotes.
6. **Hub metadata never enters `SKILL.md`.** Scope, owner, status, and subscription model live
   beside the skill in Hub storage. A skill exported from the Hub must still work unmodified with
   a plain filesystem provider — that is the guarantee that keeps the Hub from becoming a lock-in.
7. **Boring infrastructure until it hurts.** SQLite and a filesystem store until there is a
   measured reason to move. The Hub must run on a laptop, in a container, or in a customer's
   cloud without a rewrite. Azure is a deployment target, not a dependency.

## Themes

| Theme | Why it matters |
|---|---|
| **Publishing & authoring** | If getting a skill into the Hub is harder than pasting text into a prompt, nothing else on this list matters. |
| **Catalog & discovery** | An unfindable skill is an unused skill. Discovery is the difference between a store and a shared folder. |
| **Entitlement & delivery** | The Hub's actual output is a working MCP endpoint per team. Everything else is upstream of that. |
| **Governance & workflow** | Platform teams adopt this to keep control, not to lose it. Review, intake, and approval are the reason a central Hub exists at all. |
| **Trust & supply chain** | Skill text lands verbatim in an agent's context. Whoever can publish a skill can steer every agent that subscribes to it. |
| **Operability & insight** | Platform teams cannot curate what they cannot measure. Which skills are used, by whom, and did they help. |
| **Scale & multi-tenancy** | One gateway process serving many teams, with isolation that holds under review. |
| **Developer experience** | Skills are authored by engineers in editors and CI, not in web forms. Meet them there. |
| **Ecosystem** | Most organizational knowledge already exists somewhere else. Importing beats re-authoring. |
| **Project health** | An open-source project is a product; release engineering, docs, and reproducible setup are features. |

## What the Hub Needs From the SDK

The Hub is the SDK's first serious consumer, and several Hub milestones are gated on SDK work.
This table is the contract between the two repositories; each row should have a corresponding
issue in the [SDK roadmap](https://github.com/pratikxpanda/agentskills-sdk/blob/main/docs/ROADMAP.md).

| SDK capability | SDK milestone | What it unblocks here |
|---|---|---|
| Optional `version` frontmatter | v0.3 | Version pinning in subscriptions. Without it the Hub has to track versions entirely out-of-band. |
| Provider content caching | v0.3 | One gateway process serving many teams from one store, without re-reading `SKILL.md` per team per turn. |
| Resource discovery (`list_resources`) | v0.3 | Publish-time inventory, resource browsing in the catalog UI, and integrity manifests later. |
| Binary-safe resources | v0.3 | Publishing diagrams, PDFs, and screenshots without corrupting them. |
| `agentskills validate` CLI + GitHub Action | v0.4 | Authors catch errors before publish; skill repos gate their own PRs without the Hub in the loop. |
| Registry-level discovery / `register_all` | v0.4 | Composing a team registry from a subscription set without enumerating IDs by hand. |
| Catalog filtering & budget | v0.4 | Teams with large subscription sets, where the injected catalog would otherwise grow without bound. |
| Token cost reporting (`inspect --cost`) | v0.4 | Showing a team what its catalog costs per turn, which is the number the Hub is uniquely placed to own. |
| Dynamic registry add/remove | v0.6 | Subscription changes taking effect on a live gateway without a restart. |
| Skill integrity & provenance | v0.6 | Publish-time signing and a verified badge in the catalog. |
| Skill usage telemetry hooks | v0.6 | Adoption analytics sourced from the data plane rather than inferred from HTTP logs. |

---

## Now — v0.1 "Walking Skeleton"

One organization, organization scope only, open subscriptions, API-key auth. The milestone is
done when an agent that has never seen a skill answers correctly because a platform team
published one and an application team subscribed to it — with no code change on the agent side.

Breadth over depth deliberately: every layer of [DESIGN.md](./DESIGN.md) gets its thinnest
honest implementation, so the seams are found before any one layer is built out.

| Item | Theme | Area | Notes |
|---|---|---|---|
| Repository scaffolding & dev workflow | Project health | `repo` | Poetry monorepo mirroring the SDK's layout, `scripts/dev.py`, ruff/mypy/pytest, CI on every push. Same conventions as the SDK so a contributor moves between the two without relearning anything. |
| Data model & migrations | Delivery | `db` | Teams, skills, skill versions, subscriptions, API keys. Migrations from the first commit — a schema with no migration path is a schema that cannot change after the first demo. |
| Versioned skill store | Publishing | `store` | Immutable `{root}/skills/{skill_id}/{version}/{skill_id}/` layout, so a published version *is* a valid provider root and the SDK's `LocalFileSystemSkillProvider` reads it with no adapter ([ADR 0002](./adr/0002-versioned-filesystem-skill-store.md)). Re-publishing an existing version is an error, never an overwrite. |
| Publish API | Publishing | `api` | `POST /api/skills` — accept an archive, validate with the SDK's `validate_skill()` *before* anything is written, then commit atomically. Validation failures return the SDK's messages unmodified. |
| Catalog API | Catalog | `api` | List, detail, and version endpoints. The list response is what both the UI and the CLI render, so it carries description, owner, tags, latest version, and subscriber count — enough to decide without a second call. |
| Teams & API-key auth | Delivery | `auth` | Team registry plus hashed API keys. Deliberately minimal: the gateway needs to answer "which team is this" and nothing else. Entra ID replaces this in v0.4, so no identity logic leaks past the auth boundary. |
| Subscriptions API | Delivery | `api` | Subscribe, list, unsubscribe — always pinned to an explicit version. Open model only; approval gates land in v0.2. |
| Per-team MCP endpoint | Delivery | `gateway` | `/mcp/{team}` over streamable HTTP. Resolve the team from its key, compose a `SkillRegistry` from that team's active subscriptions, serve it through `agentskills-mcp-server`. This is the item the rest of the milestone exists to support. |
| Catalog & subscription UI | Catalog | `ui` | Browse, read a rendered skill, subscribe, unsubscribe, publish. Read-heavy and unglamorous, and the only artefact that makes the Hub legible to someone who will not read an OpenAPI spec. |
| Seed data & reference agent | Project health | `repo` | A seeded organization with real skills, plus a Microsoft Agent Framework agent that connects to a team endpoint. Serves as the end-to-end test and the demo simultaneously. |
| Container image & deployment | Project health | `infra` | One image, one compose file, and a documented Azure Container Apps path. Someone should be able to run the Hub without reading the source. |

---

## Next — v0.2 "Governance & Workflow"

v0.1 assumes goodwill: anyone with a key can publish, anyone can subscribe to anything. This
milestone is where the Hub earns the word *governance* — the workflows that let a platform team
say no, say later, or say "not at that version".

| Item | Theme | Area | Notes |
|---|---|---|---|
| Intake requests | Governance | `api`, `ui` | The service-catalog pattern: application teams state a need, platform teams fulfil it. Also the Hub's demand signal — an intake queue tells a platform team what to author next, which no amount of usage data can. |
| Approval-gated subscriptions | Governance | `api`, `ui` | Skills marked `approval-required` put subscriptions into `pending-approval` for the owner to decide. Needed for skills carrying regulated or sensitive procedure. |
| Multi-version publishing & upgrade | Publishing | `api`, `ui` | Several published versions per skill, an explicit upgrade action on a subscription, and a diff between two versions. A team should see what changes in its agent's instructions before accepting it. |
| Team-scoped skills & self-authoring | Publishing | `api` | Teams publish private skills under automated validation only, auto-available on their own endpoint. This is the pressure valve that stops the platform team becoming a bottleneck — and the source of future promotions. |
| `agentskills-hub` CLI | DX | `cli` | `publish`, `search`, `subscribe`, `status`, `diff`. Skills are authored in editors and shipped from terminals; a web form is not the primary interface for the people writing them. |
| Publish from CI | DX | `cli`, `repo` | A GitHub Action wrapping the CLI, so a skill repository publishes on merge. Gives Git-native authoring — history, review, blame — without the Hub having to own a Git server. |
| Notifications & webhooks | Governance | `api` | Lifecycle events (published, deprecated, approval pending, intake status) delivered by webhook. The integration seam for Teams, Slack, and everything in v0.5. |
| Deprecation & sunset | Governance | `api`, `gateway` | Mark a version deprecated with migration guidance, notify subscribers, enforce a configurable grace period before archival. Deprecation must degrade loudly and slowly, never silently. |
| Audit log | Trust | `db`, `api` | Append-only record of who published, approved, subscribed, and deprecated. The first question after a bad agent answer is "where did that instruction come from" — this is the answer. |
| Skill collections | Catalog | `api`, `ui` | A curated, version-pinned set — an "SRE starter pack" — subscribed to in one action. The subscriptions it creates are ordinary and independently removable, so nothing about delivery changes. The cheapest answer to the empty-catalog problem: a team's first day is otherwise forty decisions it is not equipped to make, and the usual response to forty decisions is to make none. |

---

## Next — v0.3 "Scale & Scope"

One organization becomes many teams and domains; one gateway process serves all of them. It is also
where the cost of a team's catalog becomes a number someone owns, rather than a side effect nobody
is measuring.

| Item | Theme | Area | Notes |
|---|---|---|---|
| Domains and scoped visibility | Scale | `db`, `api` | The three-tier scope model from the design becomes real: teams belong to domains, and the catalog a team sees is org + its domains + its own. Visibility filtering must live in one place, not per endpoint. |
| Skill promotion | Governance | `api`, `ui` | Team → domain → organization, with re-review under the target scope's rules, ownership transfer, and subscriber migration. Promotion is how good local practice becomes shared practice instead of dying in one repo. |
| Live subscription updates | Delivery | `gateway` | Subscription changes take effect on a connected agent without a restart. Depends on dynamic registry mutation in the SDK; until then the gateway rebuilds per connection. |
| Gateway multi-tenancy & caching | Scale | `gateway` | One process, many teams, shared provider cache keyed by content rather than by team. Requires an explicit isolation argument, since a cache is exactly where cross-tenant leakage happens. |
| Catalog search | Catalog | `api` | Full-text over bodies and references, not just names and descriptions. Cheap with SQLite FTS5; the search backend stays swappable. |
| Per-team environments | Delivery | `db`, `api`, `gateway` | A team holds one pinned subscription set per environment, each with its own endpoint. This is the mechanism behind "test before you upgrade" — without it, [explicit pinning](./adr/0003-explicit-version-pinning.md) asks teams to take upgrades on faith. |
| Catalog cost & budgets | Operability | `api`, `ui`, `gateway` | Show what a skill and a whole subscription set cost per turn, and let a team set a per-environment token budget enforced at subscribe time. The Hub hands teams the union of three scopes, so it is the only component that can be accountable for the total. |
| Default & mandatory skills | Governance | `api`, `db` | Organization and domain policy that places a pinned baseline skill on every team's endpoint, with visible attribution, a staged rollout window, and an audit trail ([ADR 0005](./adr/0005-default-and-mandatory-skills.md)). The one sanctioned exception to principle 4, deliberately fenced. |
| Usage telemetry | Operability | `gateway`, `db` | Which team disclosed which skill, at what level, how often. Sourced from SDK telemetry hooks rather than parsed out of access logs. |

---

## Later — v0.4 "Trust & Supply Chain"

The enterprise gate. Everything before this assumes the people with keys are trustworthy and the
skills in the store are what someone intended to publish.

| Item | Theme | Area | Notes |
|---|---|---|---|
| Entra ID / OIDC authentication | Trust | `auth` | Real identity and SSO, replacing v0.1 API keys for humans. Machine-to-machine keeps short-lived tokens. |
| Role-based access control | Trust | `auth`, `api` | Publisher, reviewer, domain lead, admin, consumer — enforced centrally, evaluated per request, with deny-by-default. |
| Skill integrity & signing | Trust | `store` | Per-file hashes recorded at publish, verified on read, and a signature chain once the SDK supports it. A skill that changed on disk after publish must fail closed. |
| Publish-time content policy | Trust | `api` | Prompt-injection heuristics, secret scanning, and a token budget applied before a version becomes publishable. The Hub is the last checkpoint before text becomes agent instruction. |
| Review workflow with required approvers | Governance | `api`, `ui` | Org-scoped publishing requires N approvals from a named group, with the review recorded against the version. |
| Tenant isolation review | Trust | `gateway` | An adversarial pass over the gateway: can team A reach team B's skill through any path — cache, error message, timing, or resource name. Findings become tests. |

---

## Later — v0.5 "Insight & Ecosystem"

Most organizational knowledge already exists somewhere. This milestone is about pulling it in and
proving that any of it works.

| Item | Theme | Area | Notes |
|---|---|---|---|
| Adoption dashboard | Operability | `ui` | Most-used skills, adoption per team, subscriptions pinned to deprecated versions, skills nobody subscribed to. The last one is the most useful and the least flattering. |
| Catalog health & staleness | Operability | `api`, `ui` | Review-by dates, "unreviewed for twelve months", and orphaned-owner detection when a team is dissolved. Catalog rot is how internal catalogs die: nothing in the system currently decays, so stale instructions reach production agents indefinitely and look exactly like fresh ones. |
| Consumer feedback loop | Operability | `api`, `gateway` | A path for "this skill was wrong" to reach the skill's owner from the place it went wrong, carrying the skill, version, and disclosure context. Usage telemetry says a skill was read; only this says whether it helped, and it is the only mechanism that makes the catalog improve rather than merely grow. |
| Skill effectiveness signals | Operability | `api` | Wire the SDK's evaluation harness into publish, so a version carries a measured with/without-skill delta rather than an author's confidence. Turns catalog ranking into something defensible. |
| External skill sources | Ecosystem | `api` | Connectors that normalise Git repositories, `AGENTS.md`, `copilot-instructions.md`, and wiki exports into skills. Attacks the empty-catalog problem, which is the real adoption barrier. |
| Skill bundles | Ecosystem | `cli`, `store` | Export a subscription set as a portable, verifiable archive; import it into an air-gapped Hub. Also the disaster-recovery story. |
| Intake integrations | Ecosystem | `api` | Bi-directional sync with Jira, Azure DevOps, and ServiceNow so intake lives where the work already is. |
| Recommendations | Catalog | `api` | "Teams like yours also subscribe to…", derived from subscription patterns. Cheap, and it addresses the discovery problem that search does not. |
| Hub-to-hub federation | Ecosystem | `api` | Mirror a curated set of skills between Hub instances across organizational boundaries. |

---

## v1.0 — Production

| Item | Notes |
|---|---|
| PostgreSQL backend | SQLite is the default for single-node and development; Postgres becomes the supported path for multi-instance. Both behind the same repository interface. |
| Horizontally scalable gateway | Stateless gateway instances behind a load balancer, with shared cache and session affinity where the transport needs it. |
| API freeze & versioning | `/api/v1` frozen and documented. Anything undocumented is explicitly private. |
| SLOs and runbooks | Stated availability and latency targets for the gateway, with alerting and operational runbooks to match. |
| Backup, restore, and disaster recovery | Tested restore of both the metadata database and the content store, including a documented RPO/RTO. |
| Multi-organization deployment | One deployment serving several organizations with hard isolation, for hosted-service scenarios. |

---

## Explicit Non-Goals

Stating these prevents recurring proposals and scope creep.

- **Executing skill scripts.** The Hub stores and serves scripts; it never runs them. Sandboxed
  execution belongs to the host application. We document the hazard, we do not own it.
- **Being an agent framework or an agent runtime.** The Hub delivers skills to agents that other
  people run. It does not host, schedule, or orchestrate agents.
- **Re-implementing the SDK.** Any retrieval, parsing, or MCP logic that appears in the Hub is a
  bug report against the SDK that has not been filed yet.
- **A proprietary skill format.** Content stays `SKILL.md` per the
  [open specification](https://agentskills.io/specification). Hub metadata lives beside the skill,
  never inside it.
- **A general knowledge base.** The unit is a skill. The Hub is not a wiki, a CMS, a document
  store, or a prompt playground, and resisting each of those is a recurring job.
- **Being an identity provider.** The Hub federates to an existing IdP. It does not own user
  accounts, passwords, or group membership.

---

## How We Plan Work

| Artifact | Purpose |
|---|---|
| **[DESIGN.md](./DESIGN.md)** | The stable model — actors, scopes, lifecycle, data model, deployment shapes. Changes rarely; when it does, the roadmap follows. |
| **[GLOSSARY.md](./GLOSSARY.md)** | The precise meaning of the words the other documents rely on. Terms like *scope*, *skill*, and *subscription* are ordinary English used as exact technical terms here. |
| **This roadmap** | Direction and sequencing. Reviewed at the start of each minor version. No dates. |
| **GitHub Milestones** | One per minor version (`v0.1`, `v0.2`, …). An item is committed when it has an issue in a milestone. |
| **GitHub Issues** | The single unit of work. Status, assignment, discussion, and linked PRs. Labelled by `theme:*`, `area:*`, `type:*`, and `good-first-issue`. |
| **[docs/issues/](./issues/)** | The durable specification behind each roadmap item, one file per milestone. Filed issues link back here instead of duplicating the text; shipped items stay for the record. |
| **[docs/adr/](./adr/)** | Short, immutable records of decisions already made and their trade-offs. Written when a decision is hard to reverse or likely to be questioned later. |

**Contributing to the roadmap:** open a GitHub Discussion for an idea, or an issue for something
concrete. Changes to a public contract — the REST API, the MCP surface, or the store layout —
should be agreed on the issue before a PR is opened.

