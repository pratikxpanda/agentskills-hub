# Contributing to Agent Skills Hub

Thank you for your interest in contributing.

**The project is at the design stage.** There is no implementation yet, which changes what is most
useful to contribute: reasoned disagreement with the design is worth more right now than code.

## Code of Conduct

Be respectful and constructive. Harassment, discrimination, and abusive behavior will not be
tolerated.

## What is most useful right now

| Contribution | Where |
|---|---|
| Disagreement with the model — a scope, lifecycle, or workflow that would not survive contact with your organization | An issue against a section of [docs/DESIGN.md](docs/DESIGN.md) |
| Disagreement with a decision | An issue referencing the [ADR](docs/adr/README.md) — ADRs are immutable, so a change means a new ADR superseding the old one |
| A missing acceptance criterion, or one that cannot be verified | A PR against the relevant [milestone spec](docs/issues/) |
| A requirement the roadmap does not cover | A [Discussion](https://github.com/pratikxpanda/agentskills-hub/discussions), or an issue if it is concrete |
| Implementation of a specified item | A PR — see below |

Before implementing, check that the item has a spec in [docs/issues/](docs/issues/) and an open
issue. If it has neither, open the issue first: the specs exist so that implementation starts from
an agreed contract rather than from a guess about one.

## Getting started

### Prerequisites

- Python 3.12, 3.13, or 3.14
- [Poetry](https://python-poetry.org/) 2.0+
- Node.js 20 LTS for the web UI

### Development setup

```bash
git clone https://github.com/pratikxpanda/agentskills-hub.git
cd agentskills-hub
poetry install
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full guide — layout, layering rules, task
runner, and testing strategy.

## Reporting issues

Issue forms are configured, so choose the template that fits:

- **Bugs:** the bug report form. Note that "described in the docs but not implemented" is not a
  bug — the roadmap says as much.
- **Feature requests:** the feature request form. Check the [roadmap](docs/ROADMAP.md) first,
  including the **non-goals** section — some things are deliberately out of scope, and the
  reasoning is written down.
- **Roadmap items:** the roadmap item form, for work that already has a spec in
  [docs/issues/](docs/issues/). Link the spec rather than copying it.
- **Security vulnerabilities:** **do not open a public issue.** Follow [SECURITY.md](SECURITY.md).

Labels are defined in [`.github/labels.yml`](.github/labels.yml) and synced automatically; the
meaning of each `theme:` and `area:` value is in [docs/issues/README.md](docs/issues/README.md).

## Pull request process

1. Fork and branch: `git checkout -b feat/my-feature`.
2. Make your changes with tests.
3. Run checks locally:
   ```bash
   python scripts/dev.py check
   python scripts/dev.py test
   ```
4. Commit with a clear message (see below).
5. Open a PR against `main`, linking the issue and the milestone spec section it implements.
6. Address review feedback.

### What makes a good PR

- **Focused.** One item per PR.
- **Tested.** Including the failure paths, not only the happy one.
- **Traceable.** Link the spec section; if the implementation diverged from it, update the spec in
  the same PR. The spec records the conclusion, the issue records the discussion.
- **Passing CI.** Lint, format, types, and tests.

### Non-negotiable review criteria

These come straight from the architecture decisions and are not treated as style preferences:

| Criterion | Reference |
|---|---|
| No `SkillProvider` implementation, frontmatter parsing, or MCP tool definition in this repository. If the SDK is missing something, file an SDK issue and document the interim behaviour. | [ADR 0001](docs/adr/0001-hub-is-a-control-plane.md) |
| Hub metadata never written into `SKILL.md`. | [ADR 0001](docs/adr/0001-hub-is-a-control-plane.md) |
| Authorisation is taken from the authenticated principal, never from a URL segment. | [ADR 0004](docs/adr/0004-multi-tenant-mcp-gateway.md) |
| Any endpoint with a team segment ships with a cross-tenant isolation test. | [ADR 0004](docs/adr/0004-multi-tenant-mcp-gateway.md) |
| Nothing changes a subscribed team's prompt surface without that team acting — except organization policy, which carries its own obligations and is not extended casually. | [ADR 0003](docs/adr/0003-explicit-version-pinning.md), [ADR 0005](docs/adr/0005-default-and-mandatory-skills.md) |
| A skill's `status` is version-level and its `lifecycle` is skill-level. Collapsing the two is the schema mistake this project is most likely to make. | [DESIGN.md](docs/DESIGN.md#skill-lifecycle) |
| Anything handling uploaded archives or user-supplied paths ships with hostile-input tests. | [v0.1 item 3](docs/issues/v0.1.md) |
| Skill content is rendered as sanitised markdown with raw HTML disabled. | [v0.1 item 9](docs/issues/v0.1.md) |

## Code style

- Type hints on all public functions and methods.
- Google-style docstrings for public APIs.
- `py.typed` markers in every package.
- Ruff for linting and formatting, line length 100.

## Commit messages

Imperative mood, prefixed by category:

```text
feat: add per-team MCP endpoint
fix: reject archive members that escape the extraction root
test: add cross-tenant isolation tests for the catalog API
docs: record the version pinning decision as ADR 0003
chore: pin CI actions to commit SHAs
```

Prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`.

## Contributing to the SDK instead

If your change belongs in skill parsing, retrieval, validation, or the MCP tool surface, it
belongs in the [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk), not here. The
[dependency table](docs/ROADMAP.md#what-the-hub-needs-from-the-sdk) lists the upstream work the Hub
is waiting on — those are among the highest-leverage contributions to this project.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
