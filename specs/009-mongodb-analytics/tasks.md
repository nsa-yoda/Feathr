# Tasks: MongoDB Analytics

## Phase 1: Setup and contract

- [X] T001 Create Feature 009 specification, clarification record, plan, checklist, research, data model, quickstart, and stats contract.
- [X] T002 Update API, traceability, and AI workflow documentation for canonical Mongo analytics.

## Phase 2: Pipeline and route foundation

- [X] T003 Implement bounded UTC range, typed stats models, and deterministic `$dateTrunc` pipeline builder in `src/event_platform/api/routes/stats.py`.
- [X] T004 Include the stats router in `src/event_platform/main.py` and map missing/dependency/decode failures to safe 503 responses.

## Phase 3: User Story 1 — aggregate canonical events (P1)

- [X] T005 [US1] Execute Mongo aggregation with early `$match`, bucket truncation, event-type grouping, and stable sort.
- [X] T006 [US1] Add unit tests for hour/day/Monday-week boundaries, multiple event types, empty results, ordering, and no raw-event Python counting.

## Phase 4: User Story 2 — bounded ranges (P1)

- [X] T007 [US2] Wire default previous-24-hour range, explicit inclusive dates, and all invalid range/bucket cases.
- [X] T008 [US2] Add route tests for defaults, partial/reversed/overlong/naive/non-UTC ranges, safe problem responses, and dependency failure.

## Phase 5: User Story 3 — canonical semantics and acceptance (P2)

- [X] T009 [US3] Add real Mongo integration coverage for known timestamps crossing hour/day/week boundaries and document canonical versus derived-store semantics.
- [X] T010 Run analyze, converge, staff/comprehensive review, targeted remediation, and final quality gates.

## Dependencies and execution order

- T001 precedes implementation.
- T003/T004 establish the route and pipeline before story tests.
- T005/T006 establish aggregation behavior before range completion T007/T008.
- T009/T010 follow documentation, convergence, and review.
