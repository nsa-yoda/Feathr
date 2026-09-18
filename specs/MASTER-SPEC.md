# Master Spec-of-Specs

This file defines the boundaries between feature specifications. It is not a replacement for feature-level Spec Kit artifacts.

## Global outcome

Produce a maintainable, production-oriented distributed event processing service that demonstrates deliberate semantics under failure, clear data ownership, testable async behavior, safe search/cache design, and exceptional reviewer usability.

## Cross-feature invariants

- Mongo canonical / ES derived / Redis non-authoritative.
- local queue 202 acknowledgement is process-volatile.
- one app process in demo.
- at-least-once + idempotency, never exactly-once claims.
- Change Stream checkpoint advances only after ES success.
- ES rebuild cannot switch alias before verification.
- Redis loss causes cache bypass and local rate-limit fallback.
- no arbitrary metadata field expansion in ES.
- no offset pagination on high-volume event/search lists.
- rate limiting is mandatory.
- every unbounded resource has an explicit bound.

## Feature-boundary rule

A feature owns its behavior and exposes a small contract to later features. Later features should consume that contract instead of reaching through layers. For example, the worker consumes a queue port and repository port; HTTP routes do not manipulate Mongo collections directly.

## Review strategy

Feature reviews happen incrementally. At the end, Feature 025 triggers a whole-repository review focusing on architectural drift, dead code, documentation mismatch, test blind spots, and whether reviewer flows actually work from a clean environment.
