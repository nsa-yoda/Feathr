---
description: "Asynchronous POST /events validation and queue handoff"
---

# Feature Specification: Async Ingestion API

**Feature Branch**: `005-ingestion-api`  
**Created**: 2026-09-18  
**Status**: Ready for review

## Clarifications

- The route creates a `CanonicalEvent` and enqueues its JSON envelope; it never writes Mongo synchronously.
- `Idempotency-Key` is validated and hashed into the envelope. Durable duplicate semantics belong to Feature 006.
- The server always owns `X-Request-ID`; inbound values are ignored by the existing middleware.
- Queue saturation is a `503` problem response with `Retry-After: 1`; validation remains `422`.

## Functional Requirements

- **FR-001**: `POST /events` MUST validate the complete Feature 002 event input before enqueueing.
- **FR-002**: Successful requests MUST construct a canonical event, enqueue it, and return `202` with immutable event ID, `queued` status, and request ID.
- **FR-003**: The route MUST NOT write Mongo synchronously or claim crash-durable acceptance.
- **FR-004**: Queue capacity timeout MUST return `503` with `Retry-After` and a safe problem response.
- **FR-005**: Optional `Idempotency-Key` MUST be printable ASCII, 1–256 characters, and carried only as its canonical hash.
- **FR-006**: OpenAPI MUST declare 202, 422, and 503 response contracts.

## Success Criteria

- Tests prove enqueue-before-202, validation problems, queue saturation, request ID ownership, idempotency redaction, and OpenAPI declarations.
