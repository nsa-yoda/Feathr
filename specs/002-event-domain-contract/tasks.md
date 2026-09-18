---
description: "Dependency-ordered tasks for Event Domain Contract"
---

# Tasks: Event Domain Contract

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, and `contracts/domain.md`.

**Tests**: Required for every user story. Keep the domain suite pure and external-service free.

## Phase 1: Setup

- [X] T001 Confirm Feature 001's domain package and strict quality tooling are available; record Feature 002 workflow artifacts under `specs/002-event-domain-contract/`.
- [X] T002 [P] Add the Feature 002 domain contract, data model, quickstart, and research documentation.

## Phase 2: Foundational Domain Helpers

- [X] T003 Define bounded JSON metadata types, contract constants, and safe validation error categories in `src/event_platform/domain/events.py`.
- [X] T004 [P] Write recursive metadata boundary tests, including Unicode, finite-number, key, depth, list, string, and serialized-size cases in `tests/unit/test_event_domain.py`.

**Checkpoint**: Metadata validation is deterministic, bounded, and independently tested before canonical event creation is added.

## Phase 3: User Story 1 - Validate producer input (P1)

- [X] T005 [US1] Implement `EventInput` scalar validation for event type, user ID, timezone-aware timestamp, future skew, HTTP(S) URL, and extra server-field rejection in `src/event_platform/domain/events.py`.
- [X] T006 [P] [US1] Add valid, invalid, boundary, UTC normalization, URL, and safe-error tests in `tests/unit/test_event_domain.py`.

## Phase 4: User Story 2 - Enforce metadata limits (P1)

- [X] T007 [US2] Implement recursive metadata validation and compact UTF-8 serialized-size checking without logging arbitrary values.
- [X] T008 [P] [US2] Add exact-boundary and over-limit regression tests for every metadata rule.

## Phase 5: User Story 3 - Create canonical event (P1)

- [X] T009 [US3] Implement deterministic producer-payload canonicalization and SHA-256 hashing with recursively sorted keys.
- [X] T010 [US3] Implement `CanonicalEvent.from_input` with injectable UUID/clock values, schema version, ingestion time, and hashed idempotency key.
- [X] T011 [P] [US3] Add repeated hash stability, key-order equivalence, changed-value, server-field exclusion, and raw-key redaction tests.

## Phase 6: Quality and Review Gate

- [X] T012 Run Feature 002 focused tests, full unit regressions, Ruff format/lint, and strict mypy; record exact evidence in `CODEX_WORK.LOG`.
- [X] T013 Run `$speckit-analyze` and resolve all critical consistency findings across spec, plan, checklist, and tasks.
- [X] T014 Run `$speckit-converge`; implement any appended work and rerun until no new tasks remain.
- [X] T015 Run staff review and comprehensive review extensions; remediate all Blocker/Critical findings and record the approved report under `reviews/`.
- [X] T016 Update requirements traceability and AI workflow evidence for Feature 002, then commit the completed spec on `main`.

## Dependencies

- T001-T004 precede user story implementation.
- T005-T006 and T007-T008 can proceed in parallel after foundational helpers; T009-T011 depend on validated input.
- T012-T016 follow all implementation and test tasks.
