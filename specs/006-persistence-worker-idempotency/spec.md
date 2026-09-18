---
description: "Persistence worker with ack-after-Mongo and idempotent redelivery"
---

# Feature Specification: Persistence Worker and Idempotency

**Feature Branch**: `006-persistence-worker-idempotency`  
**Created**: 2026-09-18  
**Status**: Ready for review

## Clarifications

- The worker verifies an existing event's payload hash before acknowledging a duplicate delivery.
- A conflicting duplicate is never overwritten. The worker invokes a conflict disposition hook owned by Feature 007; without a hook it leaves the message unacknowledged for later redrive.
- Optional HTTP idempotency keys remain hash-only. Because the local queue is volatile and Feature 005 assigns event IDs before enqueue, repeated requests with the same key cannot be globally collapsed before enqueue; the guarantee is worker-level event identity safety.
- Worker concurrency is bounded by a configured positive integer.

## Functional Requirements

- **FR-001**: The worker MUST receive queue deliveries and decode canonical event envelopes without synchronous network I/O.
- **FR-002**: The worker MUST acknowledge only after successful insert or verified same-hash duplicate.
- **FR-003**: Same event ID with a different payload hash MUST never overwrite Mongo and MUST be classified as a permanent conflict.
- **FR-004**: Conflict disposition MUST be delegated to a hook for Feature 007 DLQ handling; absent a hook, the receipt remains unacknowledged.
- **FR-005**: Worker concurrency MUST be bounded and duplicate metrics MUST be observable through a safe snapshot.
- **FR-006**: Crash-equivalent failures before ack MUST remain safe on redelivery.

## Success Criteria

Tests prove ack ordering, idempotent duplicate handling, conflict preservation, bounded concurrency, and crash-before-ack behavior using fakes plus real Mongo integration when configured.
