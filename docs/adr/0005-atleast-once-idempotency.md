# ADR 0005: Use at-least-once processing plus idempotent persistence

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Assume duplicates. Give every event an immutable ID and enforce Mongo uniqueness. Compare a stable payload hash when resolving duplicate event IDs.

## Rationale

At-least-once queues can redeliver after worker failure. Exactly-once claims would be false. Idempotent effects are the correct correctness primitive.

## Consequences

A duplicate with identical identity/content is acknowledged safely; identity collision with different content is a permanent conflict and must be surfaced/DLQ'd rather than overwritten.
