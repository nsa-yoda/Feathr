---
description: "Dependency-ordered tasks for MongoDB Store and Indexes"
---

# Tasks: MongoDB Store and Indexes

## Phase 1: Setup and dependency

- [X] T001 Add PyMongo 4.x dependency and lockfile entry for the Async API.
- [X] T002 Add Feature 003 spec, plan, checklist, research, data model, contract, and quickstart artifacts.

## Phase 2: Typed repository boundary

- [X] T003 Define typed query values, index definitions, and safe storage error types under `src/event_platform/storage/`.
- [X] T004 [P] Add unit tests for page validation, filter predicates, BSON mapping, and safe error messages.

## Phase 3: Canonical persistence and query

- [X] T005 Implement async insert and fetch-by-ID with duplicate/error translation.
- [X] T006 [P] Implement filtered cursor query with deterministic ordering and exclusive continuation.
- [X] T007 [P] Implement typed aggregation execution without returning raw collection access.
- [X] T008 Add unit tests for repository driver calls and exception dispositions.

## Phase 4: Index bootstrap

- [X] T009 Implement deterministic required `IndexModel` definitions and idempotent bootstrap.
- [X] T010 Add unit tests asserting exact names, ordered keys, uniqueness, and absent wildcard/metadata indexes.

## Phase 5: Integration and acceptance

- [X] T011 Add real-Mongo integration coverage for uniqueness, fetch, query ordering/continuation, and index presence.
- [X] T012 Run specify/clarify/plan/checklist/tasks/analyze and resolve consistency findings.
- [X] T013 Run converge and append any missing implementation work until clean.
- [X] T014 Run staff and comprehensive review; remediate all blockers/warnings.
- [X] T015 Update traceability, AI workflow, and `CODEX_WORK.LOG`; commit the approved feature on `main`.

## Dependencies

T001-T004 precede T005-T010. T011 depends on T005-T010 and a configured replica-set MongoDB. T012-T015 follow implementation and evidence.
