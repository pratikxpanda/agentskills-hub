# agentskills-hub-core

Domain model, skill store, and repositories for the [Agent Skills Hub](https://github.com/pratikxpanda/agentskills-hub).

This is the layer that has to survive the API being replaced. It imports no web framework, and it
is the only package that touches the filesystem — both rules are enforced in CI by import-linter
contracts, not by convention.

It composes the [Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk) rather than
reimplementing any part of it. See
[ADR 0001](https://github.com/pratikxpanda/agentskills-hub/blob/main/docs/adr/0001-hub-is-a-control-plane.md).

**Status:** scaffolding. No public API yet.
