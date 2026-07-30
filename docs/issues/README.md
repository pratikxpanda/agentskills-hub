# Issue Specifications

> Detailed write-ups for [roadmap](../ROADMAP.md) items, kept in the repo whether or not they
> have been filed as GitHub issues yet.

The roadmap says *what* and *why* in one line per item. These files carry the full
specification: problem statement, proposed approach, open questions, and acceptance criteria.

Each file covers one milestone, in the same order as the corresponding roadmap table.

| Milestone | Items | State |
|---|---|---|
| [v0.1 — Walking Skeleton](./v0.1.md) | 11 | Specified |
| [v0.2 — Governance & Workflow](./v0.2.md) | 10 | Specified |
| v0.3 — Scale & Scope | — | Not specified; see the [roadmap](../ROADMAP.md) |
| v0.4 — Trust & Supply Chain | — | Not specified; see the [roadmap](../ROADMAP.md) |
| v0.5 — Insight & Ecosystem | — | Not specified; see the [roadmap](../ROADMAP.md) |
| v1.0 — Production | — | Not specified; see the [roadmap](../ROADMAP.md) |

A milestone only gets a file once its items are concrete enough to have acceptance criteria.
The later ones are deliberately still one-liners on the roadmap.

## Relationship to GitHub Issues

| | Lives here | Lives on the issue |
|---|---|---|
| Problem statement, proposed design, acceptance criteria | yes | a link back to here |
| Status, assignee, milestone, discussion, linked PRs | | yes |

When an item is filed, add its number to the heading so the two stay connected:

```markdown
## 8. Serve a per-team MCP endpoint ([#42](https://github.com/pratikxpanda/agentskills-hub/issues/42))
```

The issue body should link back to its section here rather than duplicating it — duplicated
text is what drifts. If the design changes during implementation, **update the spec here**: the
issue thread records the discussion, this file records the conclusion.

Shipped items stay, marked `**Status:** Shipped in vX.Y`, so the reasoning behind a change
remains findable. An item whose design turned out to be wrong gets a note explaining why rather
than being quietly deleted.

## Cross-repository items

Several items depend on work in the [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk).
Those are tracked as issues **in the SDK repository** and referenced from here — the Hub does not
carry a private copy of the SDK's backlog. The dependency table lives in the
[roadmap](../ROADMAP.md#what-the-hub-needs-from-the-sdk).

A Hub item blocked on the SDK says so in its spec, links the upstream issue, and describes the
interim behaviour so the Hub item can still ship.

## Labels

| Prefix | Values |
|---|---|
| `theme:` | `publishing`, `catalog`, `delivery`, `governance`, `trust`, `operability`, `scale`, `dx`, `ecosystem`, `project-health` |
| `area:` | `api`, `store`, `gateway`, `ui`, `cli`, `db`, `auth`, `infra`, `sdk`, `repo` |
| `type:` | `bug`, `feature`, `docs`, `chore` |
| flat | `good-first-issue`, `help-wanted`, `breaking-change`, `blocked-on-sdk`, `needs-adr` |

The definitions live in [`.github/labels.yml`](../../.github/labels.yml) and are synced to GitHub
by a workflow when that file changes — edit the file, never the labels in the web UI, or the two
drift apart within a week.

`needs-adr` marks an item whose design constrains later work enough that it should not be
implemented before the decision is written down. It is a gate, not a chore.
