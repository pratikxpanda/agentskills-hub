## What this changes

<!-- One or two sentences. Link the issue and, if there is one, the spec section in docs/issues/. -->

Closes #

## Why

<!-- The problem, not the diff. If this deviates from the spec, say so here and update the spec. -->

## Review checklist

The first four are non-negotiable and are the ones a reviewer will actually check. See
[CONTRIBUTING.md](https://github.com/pratikxpanda/agentskills-hub/blob/main/CONTRIBUTING.md).

- [ ] **No SDK logic is re-implemented.** Parsing, validation, retrieval, and MCP exposure come from the SDK ([ADR 0001](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0001-hub-is-a-control-plane.md)).
- [ ] **No Hub metadata is written into `SKILL.md`.** Exported skills still work with a plain filesystem provider.
- [ ] **Authorization derives from the authenticated principal, never from a URL segment** ([ADR 0004](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0004-multi-tenant-mcp-gateway.md)).
- [ ] **Nothing changes a subscribed team's prompt surface without that team acting**, outside the fenced exception in [ADR 0005](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0005-default-and-mandatory-skills.md).
- [ ] Published version content is still immutable; no path overwrites an existing version.
- [ ] Tests cover the acceptance criteria in the spec, including the negative cases.
- [ ] Docs updated — spec, ADR, or roadmap — where this changes what they describe.

## Notes for the reviewer

<!-- Anything non-obvious: a trade-off taken, a test that is deliberately absent, a follow-up filed. -->
