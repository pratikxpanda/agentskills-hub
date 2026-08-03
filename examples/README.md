# Examples

## What is here

| Path | Purpose |
|---|---|
| `skills/` | The seed corpus — real skills, not placeholders, used by the demo, the seed script, and the end-to-end test |
| `seed.yaml` | Declarative seed manifest: teams, which skills are published at what scope, and the starting subscriptions |
| `agent/` | Two agents that connect to a team's MCP endpoint: one Microsoft Agent Framework, one LangChain |

## Running the demo from a clean clone

```bash
poetry install
python scripts/dev.py seed
```

`seed` migrates the database, publishes every skill in the manifest, applies the starting
subscriptions, and prints each team's MCP endpoint and API key. Run it twice and nothing is
duplicated. The one thing it cannot repeat is the API key: only a hash is stored, so a second run
says the key was kept rather than printing it again. `--rotate` issues a new one.

Then start the Hub and point an agent at it:

```bash
python -m uvicorn agentskills_hub_api.app:app --port 8000

export HUB_MCP_URL=http://127.0.0.1:8000/mcp/checkout-squad
export HUB_API_KEY=ashub_...              # printed by seed
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
export AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
export AZURE_OPENAI_API_VERSION=2024-12-01-preview

pip install agent-framework --pre "agentskills-mcp-server[agentframework]"
python examples/agent/agent_framework_hub.py

pip install langchain langchain-openai langchain-mcp-adapters
python examples/agent/langchain_hub.py
```

Both scripts print `[SKIP]` and exit cleanly when a dependency or an environment variable is
missing, so running them tells you what is not configured rather than a stack trace.

Neither script imports anything from the Hub. They speak MCP to a URL, which is the whole point:
the Hub is not a library an agent takes a dependency on.

## What the agents demonstrate

The agent's own instructions are one sentence. Everything it knows about which skills exist, what
they are for, and how to read them arrives from the team's endpoint at run time. Change the team's
subscriptions and the same process, unrestarted, sees a different catalog on its next run. That is
the claim the Hub exists to make, and it is why the demo is worth running rather than reading.

## The point of the seed corpus

An empty Hub demonstrates nothing, and a Hub seeded with `foo-skill` demonstrates slightly less. The
corpus is deliberately shaped to exercise the parts of the model that are easy to get wrong:

- **`incident-response`** is organization-scoped and openly subscribable — the ordinary case. It is
  vendored byte for byte from the
  [SDK's examples](https://github.com/pratikxpanda/agentskills-sdk/tree/main/examples/skills), so
  the same files demonstrably work through a plain filesystem provider and through the Hub. That is
  the guarantee in [ADR 0001](../docs/adr/0001-hub-is-a-control-plane.md), verified rather than
  claimed: `python scripts/dev.py examples` runs the SDK's own validator over this directory, and
  CI installs the SDK unpinned to do it.
- **`pci-payment-review`** is domain-scoped and approval-required — and neither is enforced in
  v0.1. There is no domain entity, the catalog does not filter on scope, and approval gating is not
  implemented, so the manifest records the intent and the seeder stores it as metadata. The skill
  is here so the shape is right when v0.2 makes it real; saying so is better than a demo that
  quietly implies a boundary exists.

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
