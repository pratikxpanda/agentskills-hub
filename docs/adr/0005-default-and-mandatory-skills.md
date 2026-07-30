# ADR 0005 — Organization policy may place skills on a team's endpoint

**Status:** Accepted
**Date:** 2026-07
**Areas:** `api`, `db`, `gateway`

## Context

[Principle 4](../ROADMAP.md#product-principles) states that a team's prompt surface changes only
when the team changes it. Everything in the Hub is built on it: subscriptions are explicit,
versions are pinned ([ADR 0003](./0003-explicit-version-pinning.md)), and promotion widens who may
subscribe without subscribing anyone ([DESIGN.md](../DESIGN.md#skill-promotion)).

Every organization that would deploy this will nonetheless ask for the opposite. A security
baseline, a data-handling policy, a regulated disclosure procedure — the entire reason a central
platform team exists is that some instructions are not optional. "Every team must subscribe to
`security-baseline`" is not a request that goes away when the answer is no; it gets satisfied
outside the Hub, by pasting the text into a hundred system prompts, which is exactly the
duplication the Hub was built to remove.

The choice is therefore not *whether* mandatory skills exist. It is whether they exist inside the
Hub, where they are visible, versioned, and audited, or outside it, where they are none of those.

The naive implementation is a boolean on the skill: `mandatory: true`, auto-subscribe everyone. That
is the version to avoid. It gives one person the ability to change the behaviour of every agent in
the organization by editing a row, with no window, no attribution on the receiving end, and no way
for a team to tell why an unfamiliar skill appeared on its endpoint.

## Decision

**The Hub supports organization and domain policy that places skills on team endpoints. It is the
single sanctioned exception to principle 4, and it is fenced by obligations that make it
distinguishable from a silent global rollout.**

Policy comes in two strengths:

| Strength | Behaviour |
|---|---|
| **Default** | Applied when a team or environment is created. The team may unsubscribe. Suitable for a recommended starting set. |
| **Mandatory** | Applied to all in-scope teams, present and future. The team may not unsubscribe; it may request an exemption, which is a decision recorded against the policy. |

A policy is a first-class object, not a flag on a skill:

```
Policy
 ├── id, title
 ├── scope: org | domain (with a domain reference)
 ├── strength: default | mandatory
 ├── skill: reference
 ├── version: semver (pinned — no "latest", ADR 0003 is not relaxed here)
 ├── effective_from: timestamp
 └── owner: principal reference
```

The obligations are the decision, not decoration:

| Obligation | Why |
|---|---|
| **Version-pinned.** A policy names an exact version, exactly like a subscription. Moving a policy to a new version is a distinct, audited act. | Without this, the policy owner regains precisely the silent-rewrite capability [ADR 0003](./0003-explicit-version-pinning.md) removed, for every team at once. |
| **Attributed on arrival.** Subscriptions created by policy carry `origin: policy` and name the policy and its owner. The catalog and the subscriptions page show *why* a skill is on the endpoint. | A team must never see an unexplained skill in its agent's instructions. |
| **Staged, with a window.** A new or updated policy is announced to affected teams and takes effect at `effective_from`, not on save. The default window is measured in days. | Turns an instant global change into an observable, cancellable rollout. |
| **Diffable before it lands.** Affected teams see the version diff during the window, the same view used for a voluntary upgrade. | The team cannot consent, but it can prepare — and it can raise the alarm before production changes. |
| **Audited on both sides.** Policy creation, activation, version moves, and exemptions are audit events, as are the subscriptions they create. | "Where did that instruction come from" must have a complete answer. |
| **Budget-visible.** Policy subscriptions count against the team's [catalog cost](../DESIGN.md#what-the-agent-actually-sees) and are shown in the total. | Otherwise the organization can spend a team's prompt budget invisibly. |
| **Exemptions exist and are recorded.** A team may request exemption from a mandatory policy; granting it is a decision with an owner and a reason, not a configuration change. | A mandatory set with no escape hatch gets bypassed rather than followed. |

Policy is scheduled for v0.3, after domains exist. Before that, "mandatory" has no meaningful scope
to apply to, and the correct answer to the request is a curated collection that teams subscribe to
deliberately.

## Consequences

**Good**

- The requirement is met inside the system that can make it safe, rather than outside it.
- A team can always answer why a skill is on its endpoint, and who to argue with.
- Principle 4 survives as a real constraint with one named, documented exception, instead of
  eroding into a preference the first time an enterprise asks.
- Pinning holds everywhere. There is no path in the Hub by which content changes under an agent
  without an audited act by an identified principal.

**Bad**

- Principle 4 is genuinely weakened. A team's endpoint can change because someone else acted. The
  obligations bound the damage; they do not eliminate the fact.
- Policy is a privileged capability, so the blast radius of a compromised platform-team credential
  grows. This raises the stakes on RBAC and identity in v0.4 rather than deferring them.
- More moving parts: an object with an effective date, a notification window, and an exemption
  workflow is considerably more than a boolean.

**Neutral**

- Defaults and mandatory policies share one mechanism, differing only in whether unsubscribe is
  permitted. If the distinction proves too coarse in practice, `strength` is the place to extend.

## Alternatives Considered

**Refuse outright; principle 4 is absolute.** Cleanest to state and impossible to hold. The
requirement then gets met by copy-pasting policy text into agent system prompts, where it is
unversioned, unattributed, and invisible to the Hub. Refusing to model something does not prevent
it; it prevents you from governing it.

**A `mandatory: true` flag on the skill.** Cheap and quietly dangerous. It couples the policy to the
skill record, so there is no distinct object to pin, announce, audit, or exempt from, and the
version moves whenever the owner publishes.

**Recommendation only — highlight baseline skills in the catalog and let teams subscribe.** This is
the `default` strength, and it is the right answer for most cases. It is not an answer for a control
that an auditor will ask to see evidence of.

**Enforce at the gateway instead — always serve baseline skills regardless of subscriptions.** Makes
the endpoint's contents unexplainable from the subscription list, breaks the "your subscriptions are
what your agent sees" invariant, and hides the cost. Rejected: policy must create real subscriptions
that a team can see.
