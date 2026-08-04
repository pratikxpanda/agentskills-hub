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
| Python | 3.12, 3.13, or 3.14 | Matches the SDK's supported range. |
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

```bash
python scripts/dev.py seed          # demo teams, skills, subscriptions, API keys
```

`seed` prints the team API keys and MCP endpoint URLs, and is idempotent — running it twice does
not duplicate anything. The exception is the key itself: only its hash is stored, so a second run
reports that the existing key was kept. `--rotate` issues a new one.

The whole Hub in one process, which is also what the container runs:

```bash
python scripts/dev.py dev           # API + gateway + UI on http://127.0.0.1:8000
```

Or in a container, seeded, with nothing installed but Docker:

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Repository layout

```text
agentskills-hub/
├── packages/
│   ├── core/agentskills-hub-core/        # domain model, skill store, repositories
│   ├── api/agentskills-hub-api/          # FastAPI: catalog, publish, subscriptions, auth
│   ├── gateway/agentskills-hub-gateway/  # per-team MCP endpoint
│   ├── server/agentskills-hub-server/    # composition root: API + gateway + UI in one app
│   └── cli/agentskills-hub-cli/          # v0.2
├── web/                                  # React SPA: catalog, skill, subscriptions, publish
├── deploy/                               # Dockerfile, compose, Azure Container Apps template
├── examples/
│   ├── skills/                           # seed corpus
│   ├── seed.yaml                         # teams, scopes, starting subscriptions
│   └── agent/                            # Agent Framework and LangChain reference agents
├── scripts/
│   ├── check_links.py                    # relative markdown links resolve
│   ├── check_yaml.py                     # every YAML file parses
│   ├── validate_examples.py              # examples/skills/ pass the SDK's validator
│   ├── seed.py                           # demo teams, skills, subscriptions, API keys
│   ├── sync_labels.py                    # apply .github/labels.yml to the repo
│   └── dev.py                            # task runner
├── tests/                                # end-to-end only; unit tests live beside their package
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

## Skill store

Published content lives on disk under a layout with one more level than looks necessary:

```text
{store_root}/skills/{skill_id}/{version}/{skill_id}/SKILL.md
```

The doubled `{skill_id}` is deliberate. `{store_root}/skills/{skill_id}/{version}` is handed
straight to the SDK's `LocalFileSystemSkillProvider`, and the directory inside it is the skill
directory the provider expects — so the Hub owns no retrieval code and parses no frontmatter.
[ADR 0002](adr/0002-versioned-filesystem-skill-store.md) covers the layouts that were rejected.

Publishing extracts into `{store_root}/staging/{uuid}`, validates there with the SDK's own
`validate_skill()`, and only then renames the directory into place. A version directory is either
absent or complete; the gateway may be composing a registry from the tree at the same time.

Archives are treated as hostile. `extractall` is not used even with a filter, because the size
limits have to be enforced while bytes are being read rather than after a member has landed on
disk. Traversal, absolute paths, drive letters, backslash separators, symlinks, non-regular
members, and the three bomb dimensions each have their own test with a hand-built fixture.

## Layering rules

The first three are enforced in CI by import-linter contracts, not by convention. The last becomes
a contract as the code it constrains appears.

| Rule | Why |
|---|---|
| `agentskills-hub-core` imports no web framework | It is the layer that has to survive the API being replaced. |
| `agentskills-hub-api` never touches the filesystem directly | All content access goes through the `SkillStore` protocol, so a blob-backed store is a configuration change. |
| Nothing outside `core` imports `sqlalchemy`, `sqlmodel`, or `alembic` | Persistence lives behind repositories; this is what makes the PostgreSQL move in v1.0 tractable. |
| Nothing imports `agentskills-hub-server` | It is the only package that knows both edges exist. If anything else could import it, "run the API and the gateway separately" would quietly stop being true. |
| No package implements `SkillProvider`, parses frontmatter, or defines an MCP tool | [ADR 0001](adr/0001-hub-is-a-control-plane.md). If you need one, file an SDK issue. |

Because layers above `core` legitimately reach persistence and the filesystem *through* `core`,
the last two contracts are declared `allow_indirect_imports = true`: the rule is that these
packages never do it themselves. Annotations are imports, so `core` re-exports `DatabaseSession`,
`SessionFactory`, and `DatabaseEngine` — type-annotate against those, never against SQLAlchemy.

## Authentication

A credential is `ashub_{prefix}_{secret}`: a 12-character hex prefix used to look the key up, and
a 256-bit hex secret that is never stored. Only the Argon2id hash of the secret is persisted, so a
database dump yields nothing usable.

Verification lives in `agentskills_hub_core.security` and deliberately does equal work on every
path. When a prefix is unknown, `verify_secret` still runs a full Argon2 verification against a
cached decoy hash, so an unknown prefix and a wrong secret cost the same and produce the same
`401` with the same message and no details. Revocation is checked *after* verification for the
same reason.

`agentskills_hub_core.auth.authenticate` turns a token into a `TeamPrincipal`. That is the only
place a request becomes a team.

> **Handlers take the team from the principal and never from the URL.** A `{team}` path segment
> exists for readability and cache keys. `require_team_match` compares it against the principal
> and answers `403` on disagreement — it never uses the segment to select a team.

Two operational notes:

- **The rate limiter is per-process.** `FixedWindowLimiter` counts failed authentications in
  memory, keyed by source address. It is correct for the single instance v0.1 deploys and wrong
  the moment there are two; a shared counter arrives with horizontal scaling in v0.4.
- **`last_used_at` is coalesced, not backgrounded.** `ApiKeyRepository.touch` joins the
  transaction the request already has and writes at most once per five minutes, so almost every
  authenticated request still performs no write. A `BackgroundTask` was tried first and
  deadlocked: FastAPI runs background tasks *before* `yield`-dependency teardown, so the
  request's write transaction is still open and a second SQLite connection blocks on it.

Roles do not exist yet. Any authenticated team may publish. This is a stated v0.1 limitation, not
an oversight — see the README.

## Publishing

`POST /api/skills` takes multipart form data: `archive` (tar.gz or zip), `skill_id`, `version`,
and an optional `tags` JSON array. The order inside the handler is fixed and none of it is
reorderable, because content that reaches the store reaches an agent's context verbatim:

1. Authenticate, and reject before reading a byte of the body if that fails.
2. Validate `skill_id` and `version` syntactically.
3. Refuse a version that already exists.
4. Spool the upload into the store's staging workspace, under `max_archive_bytes`.
5. Extract under the remaining limits.
6. Validate with the SDK. **Its error strings are returned verbatim**, as `error.details` — the
   Hub does not paraphrase spec errors, so an author sees what the `agentskills` CLI would say.
7. Assert frontmatter `name` equals `skill_id`.
8. Commit the staging directory, then write the `skill` and `skill_version` rows.

If step 8's database write fails after the filesystem commit, the orphaned directory is
unreferenced and invisible. Reconciliation is a v0.2 chore.

Every rejection leaves nothing under `skills/`, because everything before the commit happens
inside a staging directory that is removed in a `finally`. There is a test per rejection path
asserting exactly that.

Limits are configurable and each has its own test:

| Setting | Environment variable | Default |
|---|---|---|
| Compressed upload | `HUB_MAX_ARCHIVE_BYTES` | 20 MiB |
| Uncompressed total | `HUB_MAX_TOTAL_BYTES` | 50 MiB |
| Single file | `HUB_MAX_FILE_BYTES` | 10 MiB |
| Member count | `HUB_MAX_MEMBERS` | 2000 |

Tags are recorded when a skill is first created and ignored on later versions. Changing another
team's tags is a v0.2 question with an authorisation answer attached. They are validated and
normalised in step 2, before anything is written, so a bad tag cannot leave a stored version
behind that no row points at.

## Catalog

Four read-only endpoints, all authenticated:

| Endpoint | Returns |
|---|---|
| `GET /api/skills` | A page of entries plus `next_cursor`. |
| `GET /api/skills/{skill_id}` | One entry, plus the latest version's body and resource inventory. |
| `GET /api/skills/{skill_id}/versions` | Published versions, newest first. |
| `GET /api/skills/{skill_id}/versions/{version}` | One version's metadata and body. |

Three rules that are easy to break later:

- **Bodies are markdown and never HTML.** The content model is entirely user-submitted markdown,
  so a server-side renderer would put stored XSS one templating mistake away. Sanitisation belongs
  at render time, in the client that knows its own context.
- **The list response is a contract.** It carries every field the catalog page renders, so drawing
  a page is one request. A thin list response is the same API with the join moved into N clients.
- **`is_subscribed` and `subscribed_version` are answers about the caller**, resolved from the
  credential's environment. Skills are org-scoped and deliberately readable across teams; these
  two fields are the part that must not be.

Filtering and paging:

- `?q=` matches skill id, description, and tags. The pattern is escaped, so `%` matches a literal
  per cent rather than everything.
- `?tags=` is repeatable and combines with AND. Tags live in `skill_tag`, one row each, rather
  than in a JSON array on `skill`: portable SQL can only search a JSON array by substring, which
  matches `ops` inside `devops`.
- Pagination is cursor-based from the start. The cursor is an opaque encoding of the last
  `(skill_id, id)` seen, so a row inserted behind it neither repeats nor skips a result. Offset
  pagination would be a rewrite exactly when the catalog became large enough to need paging.

A list read is four queries regardless of page size — page, tags, subscriber counts, and the
caller's own subscriptions — rather than one plus N.

Latest version is chosen by semver precedence, not string order: `1.10.0` follows `1.9.0`, and no
portable SQL expression says so, which is why `version_sort_key` sorts in Python.

## Subscriptions

A subscription is the only thing that changes what an agent sees. Four endpoints, all scoped to
the calling team:

| Endpoint | Behaviour |
|---|---|
| `POST /api/teams/{team}/subscriptions` | `{skill_id, version}`. `201`, or `409` if already subscribed. |
| `GET /api/teams/{team}/subscriptions` | Active pins, with `latest_version` and `update_available`. |
| `PATCH /api/teams/{team}/subscriptions/{skill_id}` | Change the pinned version. |
| `DELETE /api/teams/{team}/subscriptions/{skill_id}` | Unsubscribe. Idempotent. |

Version is required and exact. `latest`, `1.x`, and `^1.0.0` are all rejected as invalid
identifiers, not interpreted — see
[ADR 0003](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0003-explicit-version-pinning.md).
A floating pin means republishing a skill rewrites the system prompt of every subscribed agent,
with no review and no way to correlate a behaviour change to a cause. The compensating feature is
`update_available` on the list, so a stale pin is visible without going looking for it.

Three rules that are easy to break later:

- **Every refusal to subscribe is the same refusal.** A missing skill, an unpublished version, a
  draft, and an archived skill all return `404 not_subscribable` with an identical body. `403`
  would confirm a skill exists, and so would a helpfully specific `404`.
- **Unsubscribing revokes, it does not delete.** Every mutation has to stay attributable to a
  principal and a timestamp, and a deleted row attributes nothing. Re-subscribing reuses the same
  row, which is also what the `(environment_id, skill_id)` uniqueness constraint requires.
- **The credential is the principal.** There are no users until v0.4, so `created_by` and
  `updated_by` hold the API key prefix. The prefix identifies the credential without being the
  secret.

Unlisted skills are subscribable. Unlisted means "not advertised", not "secret" — the same rule
the catalog detail endpoint follows.

## MCP gateway

The data plane. `agentskills-hub-gateway` serves each team its subscribed skills over MCP at
`/mcp/{team}`, and nothing else. There is also `GET /mcp/{team}/check`, which performs a real
composition and reports what it found, so a team can verify its wiring without an agent:

```console
$ curl -H "Authorization: Bearer $HUB_TOKEN" http://localhost:8000/mcp/checkout-squad/check
{"team":"checkout-squad","skill_count":2,"skills":["incident-response"],"unavailable":[]}
```

The whole of the gateway's logic is `compose()`: read the pins, point one SDK provider at each
pinned version's directory in the store, hand the registry to `agentskills-mcp-server`. **The Hub
defines no `SkillProvider`, no frontmatter parser, and no MCP tool.** If a tool is missing or
wrong, it is an SDK issue, not a Hub one. An import contract — "MCP is used only through the SDK
server" — makes that mechanical: no package here may import `mcp`, because writing a tool is what
reaching for it would mean.

Four things worth knowing before changing this:

- **The transport is stateless and the registry is per request.** `StreamableHTTPSessionManager`
  can only be run once per instance, so a stateful session would pin a client to the registry it
  first connected with, and "unsubscribing removes the skill from the next connection" would stop
  being true. Stateless makes a connection a request. The cost is re-reading each subscribed
  `SKILL.md` per request; caching is v0.3 and is gated on the SDK's provider cache.
- **Authentication happens before composition.** Composing reads the store, and an unauthenticated
  caller must not be able to cause that work. Failed attempts are throttled by the same
  `FixedWindowLimiter` the API uses — it lives in core so the two edges cannot drift apart.
- **One unreadable skill costs that skill, not the session.** A pin whose content is missing from
  the store, or that the SDK refuses to register, is skipped and named in `unavailable`. A team
  whose fifth skill is broken still gets the other four.
- **`HUB_ALLOWED_HOSTS` is not optional in a deployment.** The MCP transport enforces DNS-rebinding
  protection against an allowlist that defaults to loopback only, so a Hub behind a real hostname
  answers `421` to everything until it is set. It fails closed, and it says so in the logs.

| Variable | Default |
|---|---|
| `HUB_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*,[::1]:*` |
| `HUB_ALLOWED_ORIGINS` | `http://127.0.0.1:*,http://localhost:*,http://[::1]:*` |
| `HUB_MCP_SERVER_NAME` | `Agent Skills Hub` |

The gateway reads `HUB_DATABASE_URL` and `HUB_STORE_ROOT` too, from its own settings type rather
than the API's — an import contract forbids the two edges from depending on each other, which is
what makes running them in one process a deployment choice rather than a coupling.

`agentskills_hub_server` is where that choice is made. It is the only package allowed to know that
both edges exist, an eighth import contract forbids anything from importing it, and it is what
`python scripts/dev.py dev` and the container both run:

```python
from agentskills_hub_server import create_server_app

app = create_server_app()
```

It mounts the gateway under `/mcp`, restoring the prefix Starlette strips, and serves the built UI
from `HUB_WEB_ROOT` at `/` with a fallback to `index.html` so that a reload on a client-side route
works. Paths under `/api` and `/mcp` are excluded from that fallback: without the exclusion a
mistyped API path would return the SPA with a `200`, and the client would report a parse error
instead of the `404` it was actually given.

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
| `python scripts/dev.py seed` | Publish the demo corpus and print each team's key and endpoint |
| `python scripts/dev.py dev` | Serve the API, the gateway, and the built UI on port 8000 |
| `python scripts/dev.py e2e` | Seed, publish, subscribe, connect over MCP, assert the tool surface |
| `python scripts/dev.py migrate` | Alembic upgrade to head |
| `python scripts/dev.py migrate:down` | Alembic downgrade one revision |
| `python scripts/dev.py migration "message"` | Autogenerate a migration from the models |
| `python scripts/dev.py web:install` | `npm ci` in `web/` |
| `python scripts/dev.py web` | Lint, test, and build the UI |
| `python scripts/dev.py web:dev` | Vite dev server, proxying `/api` and `/mcp` to the Hub |

The `web` tasks are deliberately **not** part of `check`. Everything the Python side needs must
stay runnable on a machine with no Node installed; CI runs the UI as a separate job for the same
reason.

`examples` is deliberately not a local reimplementation of the spec rules, and CI installs the SDK
unpinned to run it. If a published SDK release stops accepting the example skills, that is a
finding about the Hub's central promise rather than a build to be repaired with a constraint, and
a weekly scheduled run surfaces it even when nobody is committing.

Not built yet: nothing. Every task above runs today.

Run `check` and `test` before pushing; CI runs the same commands.

## The container

[deploy/README.md](../deploy/README.md) is the operational page: configuration, persistence, the
hardening the image applies, and why `HUB_ALLOWED_HOSTS` is not optional.

What matters when changing it:

- **Base images are pinned by digest**, not by tag. Updating one means resolving a new digest, and
  Dependabot is configured to do it rather than a person remembering.
- **The runtime installs wheels, not a checkout.** Third-party versions come from `poetry.lock` via
  `poetry export`; the workspace packages are built and installed with `--no-deps`. Nothing in the
  image is an editable install pointing at a source tree that is not there.
- **Migrations run from `agentskills_hub_core.schema`**, which finds the scripts inside the
  installed package rather than through the repository's `alembic.ini`. The test suite still uses
  `alembic.ini`, on purpose: "the file a developer edits still works" is a separate claim.
- **CI starts the image, not just builds it.** The entrypoint, the migrations, the seeder, the
  non-root user, and the read-only filesystem only disagree with each other at runtime.

## Web UI

```bash
python scripts/dev.py web:install
HUB_ORIGIN=http://127.0.0.1:8000 python scripts/dev.py web:dev
```

Four pages — catalog, skill detail, subscriptions, publish — in `web/`, React and Vite, no
component library. Decisions worth knowing before changing anything there:

**The SPA is always same-origin.** The dev server proxies `/api` and `/mcp` to `HUB_ORIGIN`, and in
production the same server fronts the API and the static files. The Hub therefore ships no CORS
middleware at all, and `connect-src 'self'` in the CSP is a policy the app genuinely satisfies
rather than one relaxed on the first day it becomes inconvenient.

**The API key lives in memory for the tab, and nowhere else.** No `localStorage`, no
`sessionStorage`, no cookie. A reload signs you out; that is the trade, and a test asserts both
storages stay empty after signing in. Sign-in asks for the team slug as well as the key because
the API has no "who am I" route — every path is scoped to a slug the caller supplies.

**Skill bodies are untrusted input rendered as HTML.** Two independent layers, both of which have
been verified to be load-bearing by deliberately removing them: `marked` is configured with a
renderer that escapes raw HTML rather than passing it through, and the result goes through
DOMPurify with an allowlist of tags, two attributes, and a URL scheme regexp. `Markdown` in
`web/src/components/widgets.tsx` is the only `dangerouslySetInnerHTML` in the application. The CSP
is the third layer, and the one that assumes the first two will eventually fail.

**The CSP is injected at build time only,** by a Vite plugin, as a `<meta>` tag — the dev server
needs inline module scripts, so a policy strict enough to be worth having cannot also apply in
development. A real header from whatever serves the built files is strictly better; the meta tag
is the floor. The directive list is in `web/src/csp.ts` so that a test can assert on it.

**There is no router dependency.** `react-router-dom` carried a live high-severity advisory for a
React Server Components feature this SPA does not use, so `web/src/routes.ts` is about fifty lines
of `pushState` and `popstate`. `npm audit` runs in CI to keep that honest, in two steps:
`--omit=dev` blocks, because it covers what a user actually loads, and the full audit reports
without blocking. The distinction exists because an advisory with no published patch is a real
state — a DoS in a glob matcher reached through eslint stops no merges and ships to nobody.

## Testing

| Layer | Approach |
|---|---|
| `core` | Unit tests against a temporary store root and an in-memory database. The store's hostile-input fixtures — traversal, zip-slip, symlinks, decompression bombs — live here. |
| `api` | `httpx.AsyncClient` against the app. Every endpoint that takes a team segment has a cross-tenant test asserting team A cannot reach team B. |
| `gateway` | A real MCP client against a seeded Hub, asserting the tool surface. |
| `web` | Vitest and Testing Library against a stubbed `fetch`. The XSS corpus in `web/src/__tests__/markdown.test.ts` asserts on the parsed DOM — tags, `on*` attributes, URL schemes — because escaped text legitimately still reads as a payload in the HTML string. |
| End-to-end | `scripts/dev.py e2e`, run in CI. Lives in `tests/` rather than beside a package, because it is the one test that may know about both edges at once. It runs `scripts/seed.py` as a subprocess and authenticates with the keys that command prints, so a demo whose printed keys do not work fails here. Asserts on the MCP tool surface, never on model output, so it needs no model and does not flake. |

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
