# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please use one of the following methods:

1. **GitHub Security Advisories** (preferred): Navigate to the
   [Security Advisories](https://github.com/pratikxpanda/agentskills-hub/security/advisories/new)
   page and create a new advisory.
2. **Email**: Send a detailed report to the repository maintainers via the email address listed in
   their GitHub profile.

If the issue is in skill parsing, retrieval, or the MCP tool surface, it likely belongs to the
[Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk/security/advisories/new)
instead. If you are unsure, report it here and it will be routed.

### What to include

- A description of the vulnerability and its impact.
- Steps to reproduce the issue.
- Any relevant logs, screenshots, or proof-of-concept code.
- Suggested fix, if you have one.

### What to expect

- **Acknowledgement** within 48 hours.
- **Assessment** within 7 days — we will confirm whether the issue is accepted and provide an
  estimated timeline for a fix.
- **Fix and disclosure** — once a fix is ready, we will release a patch and publish a GitHub
  Security Advisory crediting you, unless you prefer to remain anonymous.

## Current status

The project is at the design stage and has no deployable implementation. There is nothing to
exploit yet. This policy is published early because the threat model below is a design input for
every milestone, not a document written after the fact.

## Threat Model

The Hub's defining property is that **its stored content becomes instructions to language models
acting on behalf of other teams.** Whoever can publish a skill can steer every agent subscribed to
it. That makes the Hub a high-value target in a way a document store is not.

Two consequences shape the design:

- **Skill content is untrusted, even when internally authored.** It is user-submitted markdown that
  is rendered in browsers, stored on disk, and injected into agent context verbatim.
- **Tenant isolation is the primary security property.** Team A reading team B's private
  instructions is this system's worst outcome — worse than downtime and worse than data loss,
  because it is silent.

### Primary risks and where they are addressed

| Risk | Impact | Addressed by |
|---|---|---|
| **Cross-tenant disclosure** — a team reaches another team's skills through a URL, a cache key, or an error message | Confidential procedures leak silently | [ADR 0004](docs/adr/0004-multi-tenant-mcp-gateway.md): authorisation from the principal and never the URL; per-connection registries; caches keyed by immutable content coordinates; a dedicated isolation review in v0.4 |
| **Malicious skill content** — prompt injection or misleading instructions reaching agents | Every subscribed agent is steered | Review workflow for org scope; publish-time content policy and injection scanning (v0.4); pinned versions, so a change cannot propagate silently ([ADR 0003](docs/adr/0003-explicit-version-pinning.md)) |
| **Hostile upload** — zip-slip, path traversal, symlinks, decompression bombs | Arbitrary file write on the Hub host | [v0.1 item 3](docs/issues/v0.1.md): staged extraction with member validation, resolved-path containment, size and count caps, hostile-input fixtures as merge-blocking tests |
| **Stored XSS via skill bodies** | Session theft from a user who can publish to every agent in the organization | [v0.1 item 9](docs/issues/v0.1.md): the API returns markdown and never HTML; rendering disables raw HTML, sanitises output, and runs under a CSP forbidding inline script |
| **Credential compromise** | Impersonation of a team, including publish rights | Tokens stored only as hashes, constant-time verification, revocation, rate-limited failures, no tokens in logs or errors ([v0.1 item 6](docs/issues/v0.1.md)); Entra ID and RBAC in v0.4 |
| **SSRF via webhooks** | Access to internal services from the Hub's network position | [v0.2 item 7](docs/issues/v0.2.md): HTTPS only, private and loopback ranges blocked, address validated at request time against DNS rebinding, redirects disabled, response reads capped |
| **Supply-chain tampering** — store content altered after publish | Agents receive instructions nobody approved | Immutable versions and `content_digest` from the first publish ([ADR 0002](docs/adr/0002-versioned-filesystem-skill-store.md)); verification and signing in v0.4 |
| **Unattributable change** | No answer to "where did that instruction come from" | Append-only audit log written transactionally with the change it records ([v0.2 item 9](docs/issues/v0.2.md)) |

### Explicitly not in scope

- **Executing skill scripts.** The Hub stores and serves scripts; it never runs them. Sandboxed
  execution is the responsibility of the application consuming the skill. This is a stated
  [non-goal](docs/ROADMAP.md#explicit-non-goals), and a Hub that executed uploaded scripts would be
  a remote code execution service by design.
- **Guaranteeing that skill content is correct or safe.** The Hub provides review, policy hooks,
  provenance, and audit. It cannot determine that a procedure is right.
- **Identity management.** The Hub federates to an existing identity provider from v0.4. It does
  not own accounts, passwords, or group membership.

### Inherited controls

Content retrieval, path handling, size limits, and error sanitisation are the SDK's
implementation, not a second copy inside the Hub
([ADR 0001](docs/adr/0001-hub-is-a-control-plane.md)). See the
[SDK security policy](https://github.com/pratikxpanda/agentskills-sdk/blob/main/SECURITY.md) for
those controls. A vulnerability there affects the Hub, which is a deliberate trade: one audited
implementation rather than two divergent ones.
