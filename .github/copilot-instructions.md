# Working in this repository

Agent Skills Hub — a control plane over the
[Agent Skills SDK](https://github.com/pratikxpanda/agentskills-sdk).

**The project is at the design stage.** There is no implementation yet. `docs/` describes a system
that does not exist, deliberately and in detail. Do not treat a missing module as a bug, and do not
scaffold code that no specification calls for.

| Path | Contents |
| --- | --- |
| `docs/DESIGN.md` | The stable model — actors, scopes, lifecycle, data model, deployment |
| `docs/ROADMAP.md` | Principles, themes, milestones, non-goals, and the SDK dependency contract |
| `docs/GLOSSARY.md` | Exact term meanings; check here before inventing a word |
| `docs/issues/` | Per-milestone specifications with acceptance criteria |
| `docs/adr/` | Settled decisions. Immutable — superseding one means a new ADR |
| `examples/` | Seed corpus and the demo agent |

## Branch workflow

Never commit to `main`. For every unit of work:

```bash
git checkout main
git pull --prune
git checkout -b <type>/<slug>      # feat/ fix/ docs/ chore/ ci/
# make changes, run the checks below
git push -u origin <branch>
```

The maintainer merges pull requests manually. **Do not create, update, or comment on issues or
pull requests, and do not use the `gh` CLI for that.** After a merge, sync `main` and cut a fresh
branch for the next item.

One roadmap item — or one tightly coupled cluster — per branch.

## Commands

```bash
python scripts/check_links.py           # relative markdown links resolve
python scripts/validate_examples.py     # examples/skills/ pass the SDK's own validator
```

Both run in CI on every push and pull request. Once `packages/` exists, `scripts/dev.py` gains the
same verbs as the SDK — `lint`, `format:check`, `typecheck`, `check`, `test`, `all`.

## The rules that are actually enforced

These come from the ADRs and are checked in review. They are not style preferences.

- **Never re-implement the SDK.** No `SkillProvider` implementation, no frontmatter parsing, no MCP
  tool definition in this repository. If the SDK is missing something, it becomes an issue in the
  SDK repo and the Hub ships documented interim behaviour. (ADR 0001)
- **Hub metadata never enters `SKILL.md`.** Scope, owner, status, and subscription model live
  beside the skill. A skill copied out of the store must still work with a plain filesystem
  provider — `examples/seed.yaml` demonstrates the split. (ADR 0001)
- **Authorisation comes from the authenticated principal, never from a URL segment.** A team name
  in a path is a label, not a claim. (ADR 0004)
- **Nothing changes a subscribed team's prompt surface without that team acting** — except
  organization policy, which is fenced by its own obligations. (ADR 0003, ADR 0005)
- **`skill.lifecycle` is skill-level; `skill_version.status` is version-level.** Collapsing them is
  the schema mistake this project is most likely to make.

## Conventions

- Documentation is the product right now. Write for a reader deciding whether to adopt this, not
  for one who already agreed.
- State the cost of a decision, not only the benefit. An ADR with no "Bad" section has not been
  thought through.
- Update the spec in `docs/issues/` when the design changes. The issue thread records the
  discussion; the spec records the conclusion.
- Comments explain what the code cannot show on its own. One line, not a paragraph.

## Traps worth knowing

- **Pin GitHub Actions to commit SHAs**, with the version in a trailing comment. Tags move.
- **Resolve markdown links programmatically** rather than counting `../` by eye — that is what
  `scripts/check_links.py` is for. GitHub's `../blob/main/...` shorthand does not resolve locally;
  use absolute `https://github.com/...` URLs in `.github/` templates.
- **PowerShell has no heredoc.** Use repeated `-m` flags for commit messages; embedded `` `n ``
  desynchronises the shell. Multi-line commands pasted into the integrated terminal frequently
  truncate — prefer one-liners or a script file.
- **Keep internal or event-specific material out of this repository entirely**, not merely
  gitignored. `.local/` and `*.private.md` are ignored for scratch work.
