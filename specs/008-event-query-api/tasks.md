# Tasks: Event Query API

## Phase 1: Setup and contract

- [X] T001 Create Feature 008 specification, clarification record, plan, checklist, research, data model, quickstart, and query contract.
- [X] T002 Update API/traceability documentation for canonical query and eventual search consistency.

## Phase 2: Cursor and route foundation

- [X] T003 Implement bounded signed versioned cursor codec and typed query/page models in `src/event_platform/api/routes/query.py`.
- [X] T004 Include the query router in `src/event_platform/main.py` and map missing/dependency stores to safe 503 responses.

## Phase 3: User Story 1 — browse canonical events (P1)

- [X] T005 [US1] Implement bounded `GET /events` keyset pagination using Feature 003's descending repository query.
- [X] T006 [US1] Add static-dataset pagination tests for equal timestamps, no duplicates/holes, empty pages, and next cursor behavior.

## Phase 4: User Story 2 — filters (P1)

- [X] T007 [US2] Wire event type, user, source URL, start/end, and limit validation with normalized URL/range rules.
- [X] T008 [US2] Add per-filter, combination, boundary, invalid input, and dependency failure tests.

## Phase 5: User Story 3 — consistency and acceptance (P2)

- [X] T009 [US3] Document canonical Mongo/read versus eventual Elasticsearch semantics and update traceability/AI workflow evidence.
- [X] T010 Run analyze, converge, staff/comprehensive review, targeted remediation, and final quality gates.

## Dependencies and execution order

- T001 precedes implementation.
- T003/T004 precede route stories.
- T005/T006 establish pagination before filter completion T007/T008.
- T009/T010 follow a clean convergence and final test/review pass.
