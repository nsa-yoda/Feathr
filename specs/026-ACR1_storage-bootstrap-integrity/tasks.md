---
description: "Dependency-ordered tasks for ACR1 Storage Bootstrap Integrity"
---

# Tasks: ACR1 Storage Bootstrap Integrity

**Input**: Design documents from `specs/026-ACR1_storage-bootstrap-integrity/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/storage-schema.md`

## Phase 1: Setup and Contract Baseline

**Purpose**: Fix the manifest, CLI, and validation contracts before implementation.

- [X] T001 Record the versioned collection/index manifest and compatibility rules in `specs/026-ACR1_storage-bootstrap-integrity/data-model.md` and `contracts/storage-schema.md`
- [X] T002 [P] Add failing manifest, bootstrap, verification, and safe-error unit tests in `tests/unit/test_storage_bootstrap.py`
- [X] T003 [P] Add failing production configuration and operator CLI tests in `tests/unit/test_app_settings.py` and `tests/unit/test_storage_bootstrap_cli.py`

---

## Phase 2: Foundational Storage Boundary

**Purpose**: Implement the typed versioned schema boundary used by both stories.

- [X] T004 Implement immutable collection names, operational index declarations, schema state, manifest fingerprinting, and safe classified errors in `src/event_platform/storage/bootstrap.py`
- [X] T005 Implement idempotent bootstrap and read-only compatibility/index verification in `src/event_platform/storage/bootstrap.py`
- [X] T006 Export the storage bootstrap boundary from `src/event_platform/storage/__init__.py`

**Checkpoint**: The storage boundary can bootstrap empty fake storage and reject missing or incompatible metadata without exposing raw driver errors.

---

## Phase 3: User Story 1 - Start Safely on Empty Storage (Priority: P1) 🎯 MVP

**Goal**: Every configured Mongo application verifies the canonical uniqueness and operational structures before starting background work.

**Independent Test**: Bootstrap empty storage, start the application with that database, and prove duplicate `event_id` insertion fails; remove or drift a required index and prove startup fails before task startup.

- [X] T007 [US1] Run storage verification before worker/projector creation and emit safe structured startup evidence in `src/event_platform/main.py`
- [X] T008 [US1] Reject production configuration without canonical Mongo in `src/event_platform/core/settings.py`
- [X] T009 [US1] Add lifespan ordering, cleanup, and failure-classification tests in `tests/unit/test_app_lifecycle.py` and `tests/unit/test_app_settings.py`
- [X] T010 [US1] Add real-Mongo empty-storage, uniqueness, operational-index, and incompatible-storage coverage in `tests/integration/test_storage_bootstrap_integration.py`

**Checkpoint**: User Story 1 passes unit tests and the real-Mongo test when `MONGO_URI` is available.

---

## Phase 4: User Story 2 - Govern Schema Changes Explicitly (Priority: P2)

**Goal**: A release actor applies schema version 1 idempotently while application replicas remain verification-only.

**Independent Test**: Run concurrent/repeated bootstrap commands against one database, verify one compatible marker, then run read-only verification and confirm no metadata changes.

- [X] T011 [US2] Add `storage bootstrap` and `storage verify` commands with bounded client ownership in `src/event_platform/cli.py`
- [X] T012 [US2] Add a one-shot bootstrap service and API dependency ordering in `docker-compose.yml`
- [X] T013 [US2] Add CLI concurrency, repeatability, exit-status, and secret-redaction tests in `tests/unit/test_storage_bootstrap_cli.py` and `tests/integration/test_storage_bootstrap_integration.py`

**Checkpoint**: User Story 2 proves migration ownership is separate from application startup and safe under concurrent release actors.

---

## Phase 5: Documentation, Traceability, and Acceptance

**Purpose**: Keep operational instructions and evidence aligned with the delivered guarantee.

- [X] T014 [P] Document bootstrap/verify commands, Compose ordering, production Mongo requirement, and index rationale in `README.md`, `ARCHITECTURE.md`, and `docs/adr/0010-mongo-indexes.md`
- [X] T015 [P] Update Feature 026 evidence in `docs/requirements-traceability.md`, `docs/ai-workflow-log.md`, and `CODEX_WORK.LOG`
- [X] T016 Run focused tests, `make format-check`, `make lint`, `make typecheck`, `make test-unit`, `make test-integration`, and `make test-failure`; record service availability limits in `CODEX_WORK.LOG`
- [X] T017 Run `$speckit-converge`, implement any appended tasks, and repeat until no gaps remain in `specs/026-ACR1_storage-bootstrap-integrity/tasks.md`
- [X] T018 Run staff and comprehensive review workflows, remediate blockers/critical findings, and store accepted review evidence under `specs/026-ACR1_storage-bootstrap-integrity/reviews/`
- [X] T019 Commit the completed feature and append post-commit evidence to `CODEX_WORK.LOG`

---

## Dependencies & Execution Order

- T001-T003 establish the design and failing tests.
- T004-T006 are foundational and block both user stories.
- T007-T010 complete User Story 1.
- T011-T013 complete User Story 2 and depend on the shared bootstrap boundary.
- T014-T019 follow implementation and acceptance evidence.

## Parallel Opportunities

- T002 and T003 touch separate test modules and can proceed in parallel.
- T014 and T015 cover separate documentation groups after behavior is stable.
- Unit manifest/CLI tests and real-Mongo integration preparation use separate files, but integration execution depends on the completed storage boundary.

## Implementation Strategy

1. Deliver the typed manifest and verifier with tests.
2. Wire verification-only startup and production configuration enforcement as the P1 increment.
3. Add the release-time CLI and Compose bootstrap actor as the P2 increment.
4. Reconcile documentation, run all gates, converge, review, and commit.
