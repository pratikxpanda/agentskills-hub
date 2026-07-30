# Architecture Decision Records

Short records of decisions that are hard to reverse or likely to be questioned later, with the
reasoning and the alternatives that were rejected.

An ADR is written when a choice constrains future work — store layout, delivery contracts, trust
boundaries. Routine choices do not get one; the test is whether someone six months from now would
otherwise re-open the argument without the context that closed it.

| # | Decision | Status | Areas |
|---|---|---|---|
| [0001](./0001-hub-is-a-control-plane.md) | The Hub is a control plane over the SDK, not a superset of it | Accepted | `core`, `gateway`, `store` |
| [0002](./0002-versioned-filesystem-skill-store.md) | Versioned filesystem skill store with SDK-compatible nesting | Accepted | `store`, `gateway` |
| [0003](./0003-explicit-version-pinning.md) | Subscriptions pin an exact version; there is no `latest` | Accepted | `api`, `gateway` |
| [0004](./0004-multi-tenant-mcp-gateway.md) | One multi-tenant MCP gateway, with the team resolved per connection | Accepted | `gateway`, `auth` |
| [0005](./0005-default-and-mandatory-skills.md) | Organization policy may place skills on a team's endpoint | Accepted | `api`, `db`, `gateway` |

## Conventions

**ADRs are immutable.** Once accepted, the text does not change except for typographical fixes.
Reversing a decision means writing a new ADR that supersedes it, and marking the old one
`Superseded by ADR NNNN`. The record of a decision that turned out badly is more useful than no
record at all.

**Statuses:** `Proposed` → `Accepted` → `Superseded by ADR NNNN` or `Deprecated`.

**Structure:** Context (the forces, including the option that looked obvious), Decision (what was
chosen, in the imperative), Consequences (good, bad, and neutral — an ADR with no costs listed has
not been thought through), Alternatives Considered (each with the reason it lost).

**Filename:** `NNNN-short-kebab-title.md`, numbered sequentially and never reused.

New ADRs are proposed by pull request. Discussion happens on the PR; once merged, the argument is
settled and lives here.
