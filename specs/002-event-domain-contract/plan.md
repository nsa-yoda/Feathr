# Implementation Plan: Event Domain Contract

**Branch**: `002-event-domain-contract` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Implement a pure Pydantic v2 domain contract for producer event input and immutable canonical events. Recursive metadata validation enforces explicit abuse limits; canonicalization uses deterministic compact JSON and SHA-256 so later Mongo persistence and idempotent replay can compare event semantics safely.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Pydantic v2 and the Feature 001 toolchain

**Storage**: None; Mongo serialization is deferred to Feature 003

**Testing**: pytest, Ruff, strict mypy

**Target Platform**: Async Python service domain package

**Project Type**: Web-service domain library

**Performance Goals**: Validation and hashing are linear in bounded input size and perform no network access; this feature does not establish a production latency SLO.

**Constraints**: No blocking I/O, no external services, no full metadata logging, all untrusted shape dimensions bounded.

**Scale/Scope**: Five producer fields, one canonical event envelope, and pure helpers reusable by ingestion, persistence, queue, and projection features.

## Constitution Check

- Structured boundaries: **PASS** — domain code has no infrastructure imports.
- Input abuse resistance: **PASS** — every declared string, collection, depth, and serialized-size dimension is bounded.
- Idempotency: **PASS** — immutable UUID and semantic payload hash are explicit; no exactly-once claim is made.
- Async/lifecycle: **PASS** — no I/O or long-lived resources are introduced.
- Observability/security: **PASS** — validation errors are categorized without logging arbitrary metadata or secrets.
- Testing: **PASS** — deterministic unit tests cover valid, invalid, boundary, and hashing behavior.

## Project Structure

### Documentation

```text
specs/002-event-domain-contract/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/domain.md
├── checklists/requirements.md
└── tasks.md
```

### Source and tests

```text
src/event_platform/domain/
├── __init__.py
└── events.py

tests/unit/
└── test_event_domain.py
```

**Structure Decision**: Keep the model and canonicalization helpers in the existing domain ownership package. The feature does not add HTTP routes, storage adapters, queue code, or infrastructure clients.

## Design Details

1. `EventInput` rejects extra server fields and validates scalar fields with explicit bounds.
2. Field validation plus a raw-input shape check walks metadata once, tracking depth, total keys, list lengths, scalar sizes, finite numbers, and compact UTF-8 serialized bytes before Pydantic can coerce non-JSON containers.
3. `CanonicalEvent.from_input` accepts optional injected `event_id` and `ingested_at` values for deterministic tests and hashes only a stable producer payload.
4. Idempotency keys are hashed immediately and are never retained in raw form.

## Complexity Tracking

No constitution violations or additional architectural complexity are required.
