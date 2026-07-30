# ADR 0003 — Subscriptions pin an exact version; there is no `latest`

**Status:** Accepted
**Date:** 2026-07
**Areas:** `api`, `gateway`

## Context

A subscription binds a team to a skill. It has to bind to *something* specific, and the choice is
between an exact version, a semver range, or a floating `latest`.

`latest` is what almost every package ecosystem offers and what users will ask for. It is
convenient: publish a fix, and every subscriber has it immediately. For a package registry that
convenience is usually worth its cost, because the consumer runs tests before shipping.

Skills are not packages, and the analogy breaks in a way that matters. A skill's content becomes an
agent's instructions. Republishing under a floating pin rewrites the behaviour of every subscribed
agent, in production, with no test suite in between, no rollout, and no deploy event to correlate
against. A team debugging "our agent started doing something different on Tuesday" has no signal
that anything changed on their side — because nothing did.

The version of this failure that decided the question is adversarial: with floating pins, anyone
able to publish a skill can alter the instructions of every agent subscribed to it, immediately
and everywhere. That is not a subscription model, it is a remote code path.

## Decision

**Every subscription pins an exact version. `latest`, ranges, and wildcards are not supported.**

- `POST /api/teams/{team}/subscriptions` requires an explicit `version`.
- Upgrading is `PATCH` on the subscription — a deliberate, audited act that preserves subscription
  identity and history.
- The gateway resolves a subscription to a directory path and nothing else
  ([ADR 0002](./0002-versioned-filesystem-skill-store.md)). No resolution logic exists at request
  time.

Because pinning shifts the work onto subscribers, the Hub owes them the tooling to make it cheap.
These are commitments, not nice-to-haves:

| Obligation | Milestone |
|---|---|
| Newer-version indicators in the catalog and subscription views | v0.1 |
| Structured diff between two versions, rendered before an upgrade is confirmed | v0.2 |
| Notification to subscribers when a new version is published | v0.2 |
| One-click upgrade from the notification and the subscriptions page | v0.2 |
| Deprecation with a replacement pointer and an enforced sunset period | v0.2 |
| Dashboard flagging subscriptions pinned to deprecated versions | v0.5 |

Deprecation and sunset are the deliberate answer to the strongest argument for `latest` — that a
bad or dangerous skill version must be removable without waiting for every team to act. That is a
real requirement, and it is met by a mechanism that is loud, time-bounded, and audited, rather than
by making every publish silently global.

## Consequences

**Good**

- A team's agent behaviour changes only when that team acts. Changes are correlatable to a cause.
- A skill author cannot alter production agent behaviour organization-wide by publishing.
- Rollback is trivial: re-pin the previous version, which is still present and immutable.
- Reproducibility: a support conversation can establish exactly which text an agent was given.
- Removes an entire class of resolution and cache-invalidation problems from the gateway.

**Costs**

- Fixes do not propagate automatically. A typo correction requires every subscriber to upgrade.
  Accepted, and directly mitigated by the obligations above.
- Version drift across teams is expected and must be visible, which is why the dashboard is a
  commitment rather than a possibility.
- Users will ask for `latest`. This ADR is the answer, and the answer stays no until the
  compensating tooling has shipped and the request survives it.

## Alternatives considered

- **`latest` as an opt-in per subscription.** Rejected for now. It reintroduces the failure mode
  for exactly the teams least likely to have thought about it, and the audit trail becomes
  conditional on a setting. Reconsider only once diff, notification, and deprecation have shipped
  and been used.
- **Semver ranges (`^1.0.0`).** Rejected. Ranges assume the author's minor/patch judgement predicts
  behavioural impact. For prose that steers a language model, there is no such correspondence — a
  one-word patch can change an agent's behaviour more than a rewrite.
- **Auto-upgrade with a delay window.** Rejected as the worst of both: still automatic, still
  uncorrelated with any action by the team, and now delayed enough to be harder to diagnose.
