# ADR 0002 — Versioned filesystem skill store with SDK-compatible nesting

**Status:** Accepted
**Date:** 2026-07
**Areas:** `store`, `gateway`

## Context

The Hub stores immutable, versioned skill content. The SDK's `LocalFileSystemSkillProvider`
resolves a skill as `{root}/{skill_id}/SKILL.md` and knows nothing about versions.

The natural layout is:

```text
{store_root}/{skill_id}/{version}/SKILL.md
```

It does not work. A provider rooted at `{store_root}/{skill_id}` would resolve skills by the name
of their subdirectory — the version string. `validate_skill()` would then compare the frontmatter
`name` against `1.2.0` and reject it, correctly. The layout is only usable with a Hub-owned
provider, which [ADR 0001](./0001-hub-is-a-control-plane.md) rules out.

Symlinking a per-team view directory was considered as a way to keep the natural layout. It works
on Linux, is awkward on Windows, and introduces a materialisation step that must be kept
consistent with the database.

## Decision

Nest one level further, so that every published version is *already* a valid provider root:

```text
{store_root}/
├── skills/
│   └── {skill_id}/
│       └── {version}/          <- provider root
│           └── {skill_id}/     <- skill directory the SDK expects
│               ├── SKILL.md
│               ├── references/
│               ├── scripts/
│               └── assets/
└── staging/
    └── {uuid}/                 <- extraction and validation before commit
```

Composing a team's registry then requires no Hub retrieval code at all:

```python
registry = SkillRegistry()
for sub in subscriptions:
    provider = LocalFileSystemSkillProvider(
        store_root / "skills" / sub.skill_id / sub.version
    )
    await registry.register(sub.skill_id, provider)
```

One provider per subscription is exactly what `SkillRegistry.register(skill_id, provider)` is
shaped for. Version resolution collapses into path selection, and the data plane never learns what
a version is.

Supporting rules:

- **Immutability.** A committed `{skill_id}/{version}` path is never modified. Republishing is an
  error, not an overwrite. Immutable content is what makes a pinned subscription meaningful and
  what makes `content_digest` verifiable later.
- **Atomic commit.** Extract and validate in `staging/{uuid}`, then `os.replace` the directory
  into place. A partially written version must never be visible, since the gateway may be
  composing a registry concurrently.
- **Digest at publish.** SHA-256 over the version's file tree, recorded in the database. Unused in
  v0.1 beyond duplicate detection; the anchor for integrity verification in v0.4. It cannot be
  backfilled honestly later, so it is recorded from the first publish.
- **Content and metadata are separate systems.** The store holds bytes; the database holds scope,
  owner, status, and subscriptions. Per ADR 0001, Hub metadata never enters `SKILL.md`.
- **The store is a protocol.** `SkillStore` is defined in `agentskills-hub-core` with the
  filesystem implementation behind it, so blob-backed stores can follow without touching callers.

## Consequences

**Good**

- Zero Hub-owned retrieval code. Path traversal, size limits, and error sanitisation are the SDK's
  audited implementation, in one place.
- Version pinning is a directory selection — no resolution logic, no cache invalidation problem.
- Immutability plus digests gives integrity, reproducibility, and rollback for free.
- Works identically on Windows, Linux, and any POSIX filesystem, including SMB and Azure Files.
- A version directory can be copied out and used directly with the SDK, which is the portability
  guarantee ADR 0001 promises.

**Costs**

- The doubled `{skill_id}` segment is unintuitive and requires this ADR to explain. It is
  documented at the store interface as well.
- Content is duplicated across versions; unchanged resources are stored once per version. Fine at
  the scale of organizational skill catalogs, and content-addressed storage with hard links is
  available later without changing the addressing scheme.
- Deletion is a directory tree removal, so archival must be careful about live sessions.

## Alternatives considered

- **`{store_root}/{skill_id}/{version}/SKILL.md` with a Hub-owned provider.** Rejected: violates
  ADR 0001, and re-implements the SDK's traversal and size-limit controls in a second place.
- **Materialised per-team view directories via symlinks.** Rejected: platform-specific, and adds a
  materialisation step that can disagree with the database — a correctness risk in the one
  component that must not be wrong.
- **Content-addressed blobs with a manifest per version.** Deduplicates well and is the likely
  eventual answer, but requires a Hub-owned provider to reassemble a skill from blobs. Deferred
  until deduplication is a measured problem.
- **Store content as rows in the database.** Rejected: no SDK provider can read it, large binary
  resources in a relational store are unpleasant, and it discards the portability property.
