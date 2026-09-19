# Tasks: Failure Injection and Recovery Tests

**Input**: Design documents from `/specs/020-failure-injection-tests/`
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/failure-injection.md`

## Phase 1: Deterministic Mongo, queue, and worker failures

- [X] T001 Record existing failure-suite coverage, current test count, and explicit gaps in `CODEX_WORK.LOG` and `tests/failure/README.md`.
- [X] T002 Add a deterministic Mongo outage/recovery test proving worker retry, no false acknowledgement, canonical recovery, and unhealthy Mongo/readiness state.
- [X] T003 Add a queue saturation HTTP test proving deterministic 503 problem semantics and zero accepted enqueue.
- [X] T004 Add a post-insert/pre-ack redelivery test proving one canonical record and same-payload duplicate disposition.
- [X] T005 Add retry-exhaustion coverage proving one source disposition and one allowlisted DLQ entry.

## Phase 2: Derived dependency and checkpoint failures

- [X] T006 Add Elasticsearch outage coverage proving canonical query usability, safe search 503, unchanged checkpoint, and recovery catch-up.
- [X] T007 Add stale/invalid resume-history coverage proving `reconciliation_required` and no latest-only source opening.
- [X] T008 Add Redis outage coverage proving realtime canonical bypass and conservative local rate-limit fallback without raw error leakage.
- [X] T009 Add rebuild target/verification/alias failure coverage proving old alias safety, failed state, and target cleanup.

## Phase 3: Evidence and acceptance

- [X] T010 Reconcile Feature 020 quickstart, failure README, testing strategy, traceability, and AI workflow records with exact test counts and evidence boundaries.
- [X] T011 Run `speckit-analyze`, remediate any cross-artifact gaps, and record the result.
- [X] T012 Run `speckit-converge`, append and complete any required convergence tasks, and record the result.
- [X] T013 Run staff review and comprehensive code/comments/tests/errors/types/simplify reviews; remediate blockers/warnings and write the feature-local report.
- [X] T014 Run format, lint, typecheck, unit, integration, failure, coverage, and diff gates; record service-gated limits and final counts.
- [ ] T015 Commit the approved Feature 020 implementation and docs on `main`, then perform post-commit verification.

## Dependencies & Execution Order

- Phase 1 precedes derived failure additions T006-T009 because their acceptance references queue/worker disposition semantics.
- T010 follows all test changes and precedes final reviews.
- T011-T015 are acceptance tasks after implementation and remediation.

## Implementation Strategy

1. Reuse existing protocol-shaped fakes and manual clocks; keep every injected fault local and named.
2. Implement tests around the highest-risk invariants first: no false ack, exactly-once DLQ disposition, checkpoint ordering, and alias safety.
3. Reconcile documentation and run all review/gate commands before the per-spec implementation and merge-gate commits.
