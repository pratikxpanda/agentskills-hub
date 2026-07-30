# ADR 0001 — The Hub is a control plane over the SDK, not a superset of it

**Status:** Accepted
**Date:** 2026-07
**Areas:** `core`, `gateway`, `store`

## Context

Agent Skills Hub and the [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk) are
separate repositories with overlapping subject matter. Both deal in skills, providers, registries,
and MCP. Without a stated boundary, the overlap resolves itself badly and predictably: the Hub
needs a behaviour the SDK does not have, the SDK's release cycle is slower than the Hub's, and a
"temporary" parser, provider, or MCP tool appears in the Hub and never leaves.

Three specific pressures were visible before any code existed:

- **Store layout.** The Hub versions skill content. The SDK's `LocalFileSystemSkillProvider`
  resolves `{root}/{skill_id}/SKILL.md` and has no concept of versions. The obvious response is a
  Hub-owned provider that understands versioned paths.
- **Metadata.** The Hub needs scope, owner, status, and subscription model. The skill format has
  none of these. The obvious response is extra frontmatter fields.
- **Delivery.** The Hub must expose skills over MCP. `agentskills-mcp-server` does exactly that,
  but is configured by a static file, whereas the Hub's skill set is per team and dynamic. The
  obvious response is a Hub-native MCP server.

Each obvious response is locally reasonable and collectively fatal: three of them and the Hub
contains a second, worse copy of the SDK, and skills published to the Hub stop being portable.

## Decision

**The SDK is the data plane. The Hub is the control plane. The Hub composes SDK primitives and
implements none of them.**

Concretely:

| Concern | Owner | The Hub's role |
|---|---|---|
| `SKILL.md` parsing and validation | SDK (`agentskills-core`) | Calls `validate_skill()` and surfaces its errors verbatim |
| Content retrieval | SDK providers | Instantiates providers; implements none |
| Progressive disclosure and MCP tools | SDK (`agentskills-mcp-server`) | Serves a composed registry through it |
| Which skills a team may see | Hub | Not an SDK concern |
| Versioning, review, approval, deprecation | Hub | Not an SDK concern |
| Provenance, policy, audit | Hub | The SDK offers hooks; the Hub decides |

Three consequences follow, and they are the load-bearing part of this decision:

1. **Hub metadata never enters `SKILL.md`.** Scope, owner, status, and subscription model live in
   Hub storage beside the content. A skill exported from the Hub must work unmodified against a
   plain `LocalFileSystemSkillProvider`. This is the guarantee that keeps the Hub from becoming
   lock-in, and it is why the store keeps content and metadata in separate systems.

2. **The store layout bends to the SDK, not the reverse.** The Hub stores a version at
   `{root}/skills/{skill_id}/{version}/{skill_id}/`, so that `{root}/skills/{skill_id}/{version}`
   is directly a valid provider root. The extra nesting looks redundant and buys the elimination
   of a Hub-owned provider — see [ADR 0002](./0002-versioned-filesystem-skill-store.md).

3. **Per-team delivery is composition, not a new server.** The gateway builds a `SkillRegistry`
   with one SDK provider per subscription and hands it to `agentskills-mcp-server`. Version
   resolution happens when choosing the provider's root, which is control-plane work, so the data
   plane never learns what a version is — see
   [ADR 0004](./0004-multi-tenant-mcp-gateway.md).

**When the Hub needs something the SDK lacks, the fix is an SDK issue.** The
[roadmap](../ROADMAP.md#what-the-hub-needs-from-the-sdk) tracks that dependency explicitly, and a
blocked Hub item ships with documented interim behaviour rather than a private implementation.

## Consequences

**Good**

- Skills stay portable. Content published to the Hub is readable by any SDK consumer, which keeps
  adoption reversible and therefore easier to justify.
- No duplicated retrieval logic, and no second place for a path-traversal or size-limit bug to
  hide.
- SDK improvements — caching, integrity, telemetry — arrive in the Hub as a dependency bump.
- The Hub is the SDK's first demanding consumer, which is the only reliable way to find out
  whether the SDK's abstractions are right.

**Costs**

- The Hub is gated on SDK releases for several roadmap items. Mitigated by tracking the dependency
  openly and specifying interim behaviour per item, but it is real coupling.
- The store layout carries redundant nesting that is only explicable by reference to this ADR.
- Some Hub features would be simpler with a bespoke provider. The rule is deliberately blunt
  because a case-by-case version of it always erodes.

## Alternatives considered

- **Vendor the SDK into the Hub.** Rejected. The Hub would drift from the published packages, and
  the SDK would lose its only production consumer — the relationship that keeps it honest.
- **Hub-owned versioned provider.** Rejected for v0.1. The nesting in ADR 0002 removes the need
  entirely, and once one provider is Hub-owned, the rest follow. Revisit only if a future store
  backend cannot be expressed as an SDK provider — in which case the provider belongs upstream.
- **Extend `SKILL.md` frontmatter with Hub metadata.** Rejected. It forks the format, breaks
  portability, and contradicts the SDK's own spec-first principle. Governance metadata is about a
  skill's relationship to an organization, not about the skill.
