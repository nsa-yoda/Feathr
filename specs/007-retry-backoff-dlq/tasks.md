# Tasks: Retry, Backoff, and Simulated DLQ

## Phase 1: Setup and contract

- [X] T001 Create Feature 007 specification, clarification record, plan, checklist, research, data model, quickstart, and worker contract.
- [X] T002 Document retry classifications, visibility scheduling, targeted DLQ, and queue-age semantics in architecture docs.

## Phase 2: Queue foundation

- [X] T003 Extend `src/event_platform/queue/in_process.py` with targeted dead-letter disposition, safe `DeadLetter` diagnostics, and oldest queued age while preserving existing receipt behavior.
- [X] T004 Add deterministic queue regression tests for targeted DLQ failure/success and oldest-age statistics in `tests/unit/test_in_process_queue.py`.

## Phase 3: User Story 1 — transient retries (P1)

- [X] T005 [US1] Add immutable `RetryPolicy` and injectable bounded jitter calculation in `src/event_platform/worker/persistence.py`.
- [X] T006 [US1] Integrate transient retry scheduling and unknown bounded retry handling into `PersistenceWorker` without sleeping or false acknowledgement.
- [X] T007 [US1] Add deterministic retry recovery, delay bounds, and worker-capacity tests in `tests/unit/test_retry_backoff_dlq.py`.

## Phase 4: User Story 2 — permanent failures and DLQ (P1)

- [X] T008 [US2] Classify malformed envelopes, dependency failures, immutable-ID conflicts, and unknown exceptions with stable safe reason codes.
- [X] T009 [US2] Route permanent and exhausted failures through targeted DLQ disposition and expose retry/DLQ metrics.
- [X] T010 [US2] Add tests for permanent no-retry, conflict preservation, exhaustion, diagnostics redaction, and no source ghost.

## Phase 5: User Story 3 — observation and docs (P2)

- [X] T011 [US3] Update requirements traceability, AI workflow log, and Feature 007 review evidence with current test counts.
- [X] T012 Run analyze, implement/converge recheck, staff/comprehensive review, focused re-review, and final quality gates.

## Dependencies and execution order

- T001 precedes all implementation.
- T003/T004 precede worker integration because the worker depends on targeted DLQ and age contracts.
- T005–T010 follow queue foundation; tests should be written before implementation where practical.
- T011/T012 follow a clean convergence result and all quality gates.
