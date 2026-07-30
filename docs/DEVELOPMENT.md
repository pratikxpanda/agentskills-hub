# Development Guide

> **The layout, tooling, and checks below are real.** The runtime commands — `dev`, `seed`, `e2e` —
> are not: they arrive with the API and gateway later in v0.1, and are marked as such. Any other
> divergence between this document and the code is a bug in one of them.

The conventions here deliberately mirror the
[Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk), so a contributor moving
between the two repositories relearns nothing.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 or 3.13 | Matches the SDK's supported range. 3.14 is blocked upstream. |
| Poetry | 2.0+ | Manages the monorepo; packages are installed in editable mode. |
| Node.js | 20 LTS | Only for `web/`. |
| Docker | any recent | Only for the container and compose targets. |

## Setup

```bash
git clone https://github.com/pratikxpanda/agentskills-hub.git
cd agentskills-hub

poetry install                      # all packages, editable, with dev dependencies
poetry run python scripts/dev.py migrate
poetry run python scripts/dev.py check
poetry run python scripts/dev.py test
```

The steps below are not wired up yet; they land with the API:

```bash
python scripts/dev.py seed          # demo organization, teams, skills, API keys
python scripts/dev.py dev           # API + gateway + UI
```

`seed` will print the team API keys and MCP endpoint URLs, and be idempotent — running it twice
does not duplicate anything.

## Repository layout

```text
agentskills-hub/
├── packages/
│   ├── core/agentskills-hub-core/        # domain model, skill store, repositories
│   ├── api/agentskills-hub-api/          # FastAPI: catalog, publish, subscriptions, auth
│   ├── gateway/agentskills-hub-gateway/  # per-team MCP endpoint
│   └── cli/agentskills-hub-cli/          # v0.2
├── web/                                  # React SPA (not built yet)
├── deploy/                               # Dockerfile, compose, Azure Container Apps (not built yet)
├── examples/
│   ├── skills/                           # seed corpus
│   ├── seed.yaml                         # organization, teams, scopes, starting subscriptions
│   └── agent/                            # Agent Framework and LangChain reference agents (not built yet)
├── scripts/
│   ├── check_links.py                    # relative markdown links resolve
│   ├── check_yaml.py                     # every YAML file parses
│   ├── validate_examples.py              # examples/skills/ pass the SDK's validator
│   ├── sync_labels.py                    # apply .github/labels.yml to the repo
│   └── dev.py                            # task runner
├── .github/                              # workflows, issue and PR templates, labels, CODEOWNERS
├── alembic.ini                           # migration config; the URL comes from HUB_DATABASE_URL
└── docs/
```

## Database

SQLite by default, at `./hub.db`. Override with `HUB_DATABASE_URL`; the URL must name an async
driver, so `sqlite+aiosqlite:///...` rather than `sqlite:///...`.

The schema is only ever created by Alembic — never by `SQLModel.metadata.create_all`. The tests
migrate a temporary database before every case, so a model that has drifted from its migration
fails the suite instead of passing against a schema no deployment will ever have.

Two columns carry rules worth restating, because collapsing them is the easiest mistake to make:
`skill.lifecycle` applies to a skill and all of its versions at once, and `skill_version.status`
applies to a single version. They are separate columns with separate enums.

### Layering rules

The first three are enforced in CI by import-linter contracts, not by convention. The last becomes
a contract as the code it constrains appears.

| Rule | Why |
|---|---|
| `agentskills-hub-core` imports no web framework | It is the layer that has to survive the API being replaced. |
| `agentskills-hub-api` never touches the filesystem directly | All content access goes through the `SkillStore` protocol, so a blob-backed store is a configuration change. |
| Nothing outside `core` imports `sqlalchemy`, `sqlmodel`, or `alembic` | Persistence lives behind repositories; this is what makes the PostgreSQL move in v1.0 tractable. |
| No package implements `SkillProvider`, parses frontmatter, or defines an MCP tool | [ADR 0001](adr/0001-hub-is-a-control-plane.md). If you need one, file an SDK issue. |

## Commands

`scripts/dev.py` is the single entry point. The first block matches the SDK exactly.

| Command | Behaviour |
|---|---|
| `python scripts/dev.py lint` | Ruff check |
| `python scripts/dev.py lint:fix` | Ruff check with fixes |
| `python scripts/dev.py format` | Ruff format |
| `python scripts/dev.py format:check` | Ruff format, check only |
| `python scripts/dev.py typecheck` | mypy |
| `python scripts/dev.py check` | format check + lint + typecheck + import contracts + docs |
| `python scripts/dev.py test` | pytest |
| `python scripts/dev.py test:cov` | pytest with coverage |
| `python scripts/dev.py clean` | Remove caches and build artefacts |
| `python scripts/dev.py all` | format + lint + test |

The Hub adds a few of its own:

| Command | Behaviour |
|---|---|
| `python scripts/dev.py imports` | The layering contracts in the table above, via import-linter |
| `python scripts/dev.py docs` | Every relative markdown link resolves and every YAML file parses |
| `python scripts/dev.py examples` | `examples/skills/` validate against the SDK's own `validate_skill()` |
| `python scripts/dev.py migrate` | Alembic upgrade to head |
| `python scripts/dev.py migrate:down` | Alembic downgrade one revision |
| `python scripts/dev.py migration "message"` | Autogenerate a migration from the models |

`examples` is deliberately not a local reimplementation of the spec rules, and CI installs the SDK
unpinned to run it. If a published SDK release stops accepting the example skills, that is a
finding about the Hub's central promise rather than a build to be repaired with a constraint, and
a weekly scheduled run surfaces it even when nobody is committing.

Not built yet:

| Command | Arrives with |
|---|---|
| `python scripts/dev.py seed` | Demo data |
| `python scripts/dev.py dev` | API, gateway, and UI |
| `python scripts/dev.py e2e` | End-to-end: publish → subscribe → MCP connect |

Run `check` and `test` before pushing; CI runs the same commands.

## Testing

| Layer | Approach |
|---|---|
| `core` | Unit tests against a temporary store root and an in-memory database. The store's hostile-input fixtures — traversal, zip-slip, symlinks, decompression bombs — live here. |
| `api` | `httpx.AsyncClient` against the app. Every endpoint that takes a team segment has a cross-tenant test asserting team A cannot reach team B. |
| `gateway` | A real MCP client against a seeded Hub, asserting the tool surface. |
| End-to-end | `scripts/dev.py e2e`, run in CI. Asserts on the MCP tool surface, never on model output, so it needs no model and does not flake. |

Tenant isolation tests are not optional and are not merged as follow-ups. A leak of another team's
private instructions is this system's worst failure
([ADR 0004](adr/0004-multi-tenant-mcp-gateway.md)).

## Code style

- Type hints on all public functions and methods; `py.typed` in every package.
- Google-style docstrings for public APIs.
- Ruff, line length 100, the same rule selection as the SDK.
- mypy strict on `core`.

## Working against a local SDK

Several Hub items depend on unreleased SDK work
([dependency table](ROADMAP.md#what-the-hub-needs-from-the-sdk)). To develop against a local
checkout:

```bash
poetry add --editable ../agentskills-sdk/packages/core/agentskills-core
```

Do not commit that change. A Hub commit must build against published SDK versions, otherwise CI
passes only on machines that happen to have the right checkout next door.

## Commit messages

Same convention as the SDK:

```text
feat: add per-team MCP endpoint
fix: reject archive members that escape the extraction root
test: add cross-tenant isolation tests for the catalog API
docs: record the version pinning decision as ADR 0003
chore: pin CI actions to commit SHAs
```

Prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`.

## Releasing

Versioning follows the SDK's model: all packages share one version, bumped atomically by
`scripts/bump-version.*`, released together on a tag. The Hub is deployed as a container image
rather than published to PyPI, with the CLI as the exception — it is installed by users and
publishes to PyPI from v0.2.
