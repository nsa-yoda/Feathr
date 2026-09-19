# Tasks: Mongo Change-Stream Search Projection

## Phase 1: Setup and contracts

- [X] T001 Create Feature 010 specification artifacts and record decisions in `specs/010-search-projection-changestream/`.
- [X] T002 [P] Add Elasticsearch dependency and lock metadata in `pyproject.toml` and `uv.lock`.

## Phase 2: Foundational ports and models

- [X] T003 [P] Define typed projector ports, safe status/state models, and failure classifications in `src/event_platform/search/projection.py`.
- [X] T004 [P] Add deterministic canonical event projection helpers in `src/event_platform/search/projection.py`.
- [X] T005 Implement Mongo checkpoint persistence and BSON-safe token validation in `src/event_platform/storage/checkpoints.py`.
- [X] T006 Implement async Elasticsearch alias/target write adapter and safe dependency translation in `src/event_platform/search/elasticsearch.py`.

## Phase 3: User Story 1 — project canonical inserts

- [X] T007 [US1] Implement ordered alias/target writes followed by checkpoint persistence in `src/event_platform/search/projection.py`.
- [X] T008 [P] [US1] Add unit coverage for deterministic projection, event ID identity, replay idempotency, malformed changes, and write-before-checkpoint ordering in `tests/unit/test_search_projection.py`.

## Phase 4: User Story 2 — dependency failure and retry

- [X] T009 [US2] Implement bounded injectable retry/backoff and safe degraded status transitions in `src/event_platform/search/projection.py`.
- [X] T010 [P] [US2] Add failure tests for ES outage, Mongo failure, retained checkpoint, and eventual recovery in `tests/failure/test_search_projection_failure.py`; keep target-write retention covered by the projector unit suite.

## Phase 5: User Story 3 — resume and invalid history

- [X] T011 [US3] Implement insert-only async Mongo change-stream source with valid checkpoint resume and terminal invalid-token handling in `src/event_platform/storage/change_stream.py`.
- [X] T012 [P] [US3] Add unit/integration coverage for restart resume, missing checkpoint, invalid token, cancellation, and structured status in `tests/unit/test_search_projection.py` and `tests/integration/test_search_projection_integration.py`.

## Phase 6: User Story 4 — rebuild target seam

- [X] T013 [US4] Add optional target-generation dual-write configuration and checkpoint ordering contract in `src/event_platform/search/projection.py`.
- [X] T014 [P] [US4] Add integration assertions for successful alias plus target writes in `tests/integration/test_search_projection_integration.py` and unit coverage for target failure checkpoint retention in `tests/unit/test_search_projection.py`.

## Phase 7: Polish and quality gates

- [X] T015 Update architecture, API/traceability, and AI workflow documentation with Feature 010 evidence in `ARCHITECTURE.md`, `docs/requirements-traceability.md`, and `docs/ai-workflow-log.md`.
- [X] T016 Run analyze, converge, staff/comprehensive review, targeted remediation, and final quality gates; record the report in `specs/010-search-projection-changestream/reviews/`.

## Dependencies

- T001/T002 precede implementation. T003-T006 establish shared ports before story phases.
- User Story 1 precedes User Stories 2 and 3. User Story 4 depends on the write coordinator from User Story 1 and remains compatible with Feature 012.

## Parallel opportunities

- T002, T003, and T004 can proceed in parallel.
- T008, T010, T012, and T014 are story-specific tests and can proceed after their ports exist.

## MVP scope

User Story 1 is the smallest useful increment: deterministic projection with checkpoint-after-success and replay-safe identity.
