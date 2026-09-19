# Tasks: Unit Test Coverage Closure

**Input**: Design documents from `/specs/018-unit-test-coverage/`
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/unit-coverage.md`

## Phase 1: Baseline and tooling

- [X] T001 Record the current unit-test baseline and measured coverage output with `make coverage`; keep the observed percentage out of requirements until measured.
- [X] T002 [P] Add the locked development-only coverage dependency, ignore generated `coverage/` output, and add the `make coverage` terminal/XML target in `pyproject.toml`, `uv.lock`, `.gitignore`, and `Makefile`.
- [X] T003 [P] Update `README.md`, `docs/testing-strategy.md`, `docs/requirements-traceability.md`, and Feature 018 quickstart/contract docs with coverage evidence limits and commands.

## Phase 2: User Story 1 — Durable event semantics

- [X] T004 [P] [US1] Extend `tests/unit/test_in_process_queue.py` with deterministic tuple/deep-freeze, invalid configuration/identifier, admission-stop, visibility, long-poll, stale-receipt, redrive, and close boundary cases.
- [X] T005 [P] [US1] Extend `tests/unit/test_retry_backoff_dlq.py` with finite-jitter, classification, bounded-attempt, and safe diagnostic cases using an injectable clock/jitter.
- [X] T006 [US1] Extend `tests/unit/test_persistence_worker.py` with duplicate lookup missing/failure, conflict accepted/rejected/hook-error, decode, retry, acknowledgement, and supervision state assertions.
- [X] T007 [US1] Add a focused deterministic selection for all queue/worker/retry/idempotency tests and assert no wall-clock sleeps or external dependencies are required.

## Phase 3: User Story 2 — Read-side and control-plane semantics

- [X] T008 [P] [US2] Extend `tests/unit/test_event_query_api.py` and `tests/unit/test_search.py` with all malformed, tampered, wrong-scope, extra-field, boundary, and zero-downstream-call cursor/query cases.
- [X] T009 [P] [US2] Extend `tests/unit/test_mongodb_analytics.py` with date-range, grouping, malformed bucket, bounded-result, and dependency-error behavior assertions.
- [X] T010 [P] [US2] Extend `tests/unit/test_search_mapping.py` and `tests/unit/test_search_projection.py` with deterministic nested/array metadata, unsafe response, checkpoint, and retry boundary assertions.
- [X] T011 [P] [US2] Extend `tests/unit/test_realtime_stats.py` with cache-key, schema/cardinality/temporal validation, Redis read/write bypass, TTL, malformed response, and single-flight assertions.
- [X] T012 [P] [US2] Extend `tests/unit/test_rate_limit.py` and related rate-limit unit modules with route isolation, identity normalization, malformed forwarding headers, token/refill boundaries, policy validation, and bounded eviction cases.
- [X] T013 [US2] Extend `tests/unit/test_settings.py` and `tests/unit/test_problems.py` with dependency URL/origin/timeout boundaries, safe startup diagnostics, problem mapping, and security-header assertions.

## Phase 4: Acceptance and evidence

- [X] T014 [US1] [US2] Run the Feature 018 focused selection and verify every mandatory focus area has a behavior-level assertion and no unintended dependency call where applicable.
- [X] T015 [P] Reconcile task/spec/plan/checklist/traceability/AI-workflow evidence with the measured test counts and coverage command; do not invent a percentage.
- [X] T016 Run `speckit-analyze`, `speckit-converge`, staff review, comprehensive review, targeted remediation, and all repository gates; record the final review report and timestamped work log.

## Dependencies & Execution Order

- Phase 1 must complete before measuring or documenting the final report.
- Phase 2 and Phase 3 test work can proceed in parallel after the baseline, but each remains deterministic and service-free.
- Phase 4 follows all test additions and includes the full repository gates.
