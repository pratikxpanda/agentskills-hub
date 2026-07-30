---
name: pci-payment-review
description: Review checklist and hard constraints for changes touching payment flows, card data, or PCI-DSS scope. Use when reviewing, designing, or debugging code that handles cardholder data, payment authorisation, or refunds.
---

# PCI Payment Review

Guidance for any change that touches cardholder data or the payment authorisation path.

## When this applies

This skill applies when a change touches any of:

- Card numbers, expiry dates, cardholder names, or CVV in any form
- The authorisation, capture, refund, or chargeback path
- Logging, tracing, or error handling on a code path that carries the above
- Third-party payment SDKs, tokenisation services, or gateway clients

If none of these apply, the change is out of PCI scope and this skill has nothing to say about it.
Say so explicitly rather than applying the checks anyway.

## Hard constraints

These are not preferences. A change that violates one of them does not ship.

| Constraint | Why |
|---|---|
| Never log a full PAN, CVV, or track data — not at any level, not in an exception, not in a trace | Log aggregation puts data outside the compliance boundary within seconds and it cannot be recalled |
| Never store CVV after authorisation, encrypted or otherwise | Prohibited outright by PCI-DSS; encryption does not make it permissible |
| Mask PANs to first six and last four digits everywhere they are displayed | Includes admin tooling, support views, and test fixtures |
| Use the tokenisation service; do not pass raw card data between internal services | Every service that touches raw card data enters PCI scope, and scope is the cost |
| Never place cardholder data in a URL, query string, or cache key | These are logged by intermediaries the team does not control |

## Review checklist

1. **Scope** — Does this change widen the set of services handling cardholder data? If yes, that is
   the finding; report it before reviewing anything else.
2. **Logging** — Trace every log, metric, and exception path on the changed code. Structured logging
   that serialises a whole request object is the most common way a PAN escapes.
3. **Persistence** — Check schemas, caches, queues, and temporary files, not only the primary
   database.
4. **Error handling** — Confirm failed authorisations do not include the request payload in the
   error surfaced to the client or to monitoring.
5. **Test data** — Confirm fixtures use designated test card numbers, never real or realistic ones.
6. **Third-party calls** — Confirm outbound requests carry a token rather than raw card data, and
   that the endpoint is on the approved list.

## What to do with a finding

Report the specific constraint violated, the file and line, and the minimal fix. Do not approve the
change with a comment; PCI findings block. If the correct fix is ambiguous, escalate to the payments
domain lead rather than guessing — an incorrect fix that looks compliant is worse than an open
finding.

## Out of scope for this skill

Fraud scoring, chargeback dispute handling, and settlement reconciliation are separate concerns with
their own skills. This skill covers the compliance boundary only.
