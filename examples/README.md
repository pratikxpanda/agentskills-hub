# Examples

> **Status: design stage.** The skills and the seed manifest here are real and final in shape. The
> `scripts/seed.py` and `examples/agent/` they are written for arrive with
> [v0.1 item 10](../docs/issues/v0.1.md).

## What is here

| Path | Purpose |
|---|---|
| `skills/` | The seed corpus — real skills, not placeholders, used by the demo, the seed script, and the end-to-end test |
| `seed.yaml` | Declarative seed manifest: organization, teams, which skills are published at what scope, and the starting subscriptions |
| `agent/` *(v0.1)* | A Microsoft Agent Framework agent that connects to a team's MCP endpoint |

## The point of the seed corpus

An empty Hub demonstrates nothing, and a Hub seeded with `foo-skill` demonstrates slightly less. The
corpus is deliberately shaped to exercise the parts of the model that are easy to get wrong:

- **`incident-response`** is organization-scoped and openly subscribable — the ordinary case. It is
  copied from the [SDK's examples](https://github.com/pratikxpanda/agentskills-sdk/tree/main/examples/skills),
  so the same skill file demonstrably works through a plain filesystem provider and through the Hub.
  That is the guarantee in [ADR 0001](../docs/adr/0001-hub-is-a-control-plane.md), verified rather
  than claimed.
- **`pci-payment-review`** is domain-scoped and approval-required. It proves that scope filtering
  and approval gating are real: a team outside the payments domain cannot see it in the catalog and
  cannot reach it on its endpoint.

## Hub metadata lives in `seed.yaml`, not in `SKILL.md`

This is the one thing to notice when reading these files. Scope, owner, visibility, subscription
model, and version are all in `seed.yaml`. Open any `SKILL.md` here and it is a plain skill with
`name` and `description` — nothing Hub-specific, nothing that would break if the file were handed
to someone using the SDK alone.

A skill exported from the Hub is a skill. That is what stops the Hub becoming lock-in, and it is
easier to hold to when the examples make the separation visible.

## Adding a skill here

1. Write `skills/{skill-id}/SKILL.md` with `name` and `description` in the frontmatter.
2. Add an entry to `seed.yaml` with its scope, owner, and subscription model.
3. Keep it real. A skill that no engineer would actually want tells you nothing about whether the
   catalog is useful, and the demo is more convincing when the content is worth reading.
