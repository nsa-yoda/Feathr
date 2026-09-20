# Tasks: ACR2 Runtime Correctness and Production Readiness

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, and `contracts/`

## Phase 1: P0 lifecycle safety

- [X] T001 [US1] Add regression tests for accepted-event shutdown drain, forced timeout residuals, acknowledgement redelivery, and queue-closed admission.
- [X] T002 [US1] Refactor `src/event_platform/core/lifecycle.py` to separate admission stop from drainable persistence stop and report task/residual outcomes.
- [X] T003 [US1] Enforce `TaskPolicy` criticality/degradation semantics and make canonical readiness independent of derived projector health.
- [X] T004 [US1] Update `src/event_platform/main.py` composition and operational health output for the lifecycle contract.

## Phase 2: P1 producer and projector correctness

- [X] T005 [US3] Add failing concurrency and failure-injection tests for same-key reservations, stale takeover, queue admission failure, completion races, and stable client scope.
- [X] T006 [US3] Implement owner-token/generation idempotency state transitions and explicit release/enqueued semantics in memory and Mongo adapters.
- [X] T007 [US3] Wire authenticated client scope and preserve the documented local single-client fallback.
- [X] T008 [US3] Add projector lease acquisition, renewal, fencing, and monotonic checkpoint tests and implementation.
- [X] T009 [US3] Add bounded Elasticsearch bulk projection with acknowledged-prefix checkpointing and partial retry behavior.
- [X] T010 [US3] Correct rate-limit route classification and add a bounded delayed-request admission gate with route-contract tests.
- [X] T011 [US3] Reject or explicitly replay active duplicate queue message IDs and add queue regression coverage.

## Phase 3: P2 schema, CI, docs, and security hygiene

- [X] T012 [US4] Add idempotency and projection lease/checkpoint collections to storage manifests, indexes, bootstrap, and cleanup policy.
- [X] T013 [US4] Repair CI required integration/failure/coverage gates and add a coverage threshold based on the verified backend baseline.
- [X] T014 [US4] Fix CORS header contract, metrics route normalization, local bucket eviction complexity, and safe middleware configuration caching.
- [X] T015 [US4] Update README, ARCHITECTURE, operational docs, configuration examples, AI workflow, and comments to match runtime behavior.
- [X] T016 [US4] Assess the rebuild CLI, analytics scaling, authentication scope, and placeholder packages; implement safe fixes or record evidence-backed intentional deferrals.

## Phase 4: P3 hygiene and verification

- [X] T017 [US4] Remove tracked generated/cache/archive artifacts that are confirmed irrelevant and harden `.gitignore`/archive behavior.
- [X] T018 [US4] Run formatting, lint, typecheck, unit, integration, failure, coverage, Docker, smoke, and Postman gates where available; append exact evidence to `CODEX_WORK.LOG`.
- [X] T019 [US4] Produce the final `AUTO_CODE_REVIEW_2` remediation report and commit each completed logical slice.
