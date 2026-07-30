# Glossary

Most of these words are ordinary English used here as exact technical terms. Where two of them
sound like they mean the same thing, the entry says how they differ — that is usually the reason
the entry exists.

## The unit of content

| Term | Meaning |
|---|---|
| **Skill** | A self-contained unit of expertise in the [open `SKILL.md` format](https://agentskills.io/specification): YAML frontmatter, a markdown body of instructions, and optional `references/`, `scripts/`, and `assets/`. The Hub's only unit of content. |
| **Skill version** | One immutable publication of a skill, identified by semver. Content never changes after publish; the version's *status* still can. |
| **Content digest** | SHA-256 over a version's file tree, recorded at publish. The anchor for duplicate detection now and integrity verification later. |
| **Resources** | The non-`SKILL.md` files a skill ships with. Loaded on demand, never injected into the prompt automatically. |
| **Store root** | The filesystem location holding published content, laid out as `{root}/skills/{skill_id}/{version}/{skill_id}/` so that each published version is directly a valid SDK provider root ([ADR 0002](./adr/0002-versioned-filesystem-skill-store.md)). |

## Who and where

| Term | Meaning |
|---|---|
| **Organization** | The top-level tenant. Implicit and singular until multi-organization deployment in v1.0. |
| **Domain** | A grouping of teams that share a governance boundary — payments, data platform, security. Arrives in v0.3. |
| **Team** | The unit of entitlement and authorization. A subscription belongs to a team, not to a person. |
| **Environment** | A named subscription set within a team, each with its own endpoint — `default`, `staging`, `production`. How a team tests a version bump before production sees it. Arrives in v0.3. |
| **Principal** | Whatever the Hub authenticated on a request: a team API key in v0.1, a user or machine identity from v0.4. Authorization is always derived from the principal, never from a URL segment. |
| **Actor** | A role in the design narrative — platform team, domain lead, application team, Hub admin. Actors are not database rows; roles become enforceable with RBAC in v0.4. |

## Access and entitlement

These four are the ones most often confused with each other.

| Term | Answers | Not to be confused with |
|---|---|---|
| **Scope** (`org` / `domain` / `team`) | *May this team see the skill at all?* The security boundary. | Visibility, which is only about browsing |
| **Visibility** (`listed` / `unlisted`) | *Does it appear when they browse?* A discovery preference, never a security control. | Scope |
| **Subscription model** (`open` / `approval-required`) | *Can an entitled team subscribe without asking?* | Scope — approval gates a skill the team can already see |
| **Subscription** | A team, an environment, a skill, and an exact version. The record that puts a skill on an endpoint. | Entitlement — being allowed to subscribe is not subscribing |

| Term | Meaning |
|---|---|
| **Pin** | The exact version a subscription names. There is no `latest` and there are no ranges ([ADR 0003](./adr/0003-explicit-version-pinning.md)). |
| **Upgrade** | Deliberately moving a pin to a newer version. Audited, diffable, and never automatic. |
| **Collection** | A curated, version-pinned set of skills subscribed to in one action. A publishing convenience: it creates ordinary subscriptions and the gateway knows nothing about it. |
| **Policy** | Organization or domain configuration that places a pinned skill on team endpoints — `default` (removable) or `mandatory` (not). The one sanctioned exception to "a team's prompt surface changes only when the team changes it" ([ADR 0005](./adr/0005-default-and-mandatory-skills.md)). |
| **Origin** | Why a subscription exists: `manual`, `collection`, or `policy`. What lets a team answer "why is this on my endpoint?" |

## Lifecycle

| Term | Meaning |
|---|---|
| **Publish** | Validate content with the SDK, write it immutably to the store, and record the version. The only way content enters the Hub. |
| **Draft / Review** | Version states before publication. Arrive with the review workflow in v0.4. |
| **Deprecated** | Still served to existing subscribers, flagged with migration guidance, closed to new subscriptions. Applies to a version, or to a whole skill. |
| **Sunset** | The enforced grace period between deprecation and archival. |
| **Archived** | Removed from the catalog and every endpoint. Content retained for audit, never served. |
| **Promotion** | Widening a skill's scope — team to domain to organization — with re-review and ownership transfer. It changes who *may* subscribe; it never subscribes anyone. |
| **Shadowing** | A narrower-scoped skill sharing an ID with a broader-scoped one. Resolution is deterministic and surfaced in the catalog, never silent. |
| **Intake request** | An application team's record of a skill it needs but that does not exist. The Hub's demand signal — the one thing usage data can never produce. |

## Delivery

| Term | Meaning |
|---|---|
| **MCP** | [Model Context Protocol](https://modelcontextprotocol.io). The Hub's only consumption contract: a team integrates with one URL and one token. |
| **Gateway** | The multi-tenant process serving per-team MCP endpoints. Resolves the team and environment from the credential, composes a registry from that set's subscriptions, and serves it ([ADR 0004](./adr/0004-multi-tenant-mcp-gateway.md)). |
| **Provider** | An SDK component that retrieves skill content from a source — filesystem, HTTP, Git. The Hub composes providers; it does not write retrieval code. |
| **Registry** | The SDK's in-memory collection of skills backed by providers. The gateway builds one per connection from that connection's subscriptions. |
| **Control plane / data plane** | The Hub is the control plane: catalog, entitlement, governance, publishing. The SDK is the data plane: parsing, retrieval, and MCP exposure. Logic that appears in the wrong one is a bug ([ADR 0001](./adr/0001-hub-is-a-control-plane.md)). |
| **Bundle** | A portable, verifiable archive of a subscription set at its pinned versions. The prerequisite for air-gapped self-hosting. |

## Cost

| Term | Meaning |
|---|---|
| **Catalog** | Two distinct things, unfortunately. In the **UI**, the browsable index of skills a team may see. In an **agent's context**, the list of one-line entries the SDK injects so the model knows what is available. The second is what costs tokens. |
| **Catalog cost** | Tokens a team's injected catalog consumes on every turn — roughly linear in subscription count. The Hub displays it because the Hub is the only component that can see a team's full set. |
| **Progressive disclosure** | Injecting only catalog entries and loading a skill's body when the agent asks. What makes a large catalog affordable, and the reason catalog entry size matters more than skill length. |
| **Budget** | A per-environment token ceiling. Enforced when subscribing, with the offending total named — never by silently truncating what is served. |
