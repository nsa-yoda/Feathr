# Tasks: Online Elasticsearch Rebuild

## Phase 1: Setup
- [X] T001 Create Feature 012 Spec Kit artifacts and record accepted decisions in `specs/012-elasticsearch-online-rebuild/`.

## Phase 2: Foundational
- [X] T002 [P] Define bounded rebuild models, lease state, ports, and safe failures in `src/event_platform/search/rebuild.py`.
- [X] T003 [P] Implement Mongo compare-and-set rebuild lease/state adapter in `src/event_platform/storage/rebuilds.py`.
- [X] T004 [P] Implement Elasticsearch generation, bulk, count, and atomic alias adapter in `src/event_platform/search/elasticsearch_rebuild.py`.

## Phase 3: User Story 1 - lease and state
- [X] T005 [US1] Implement exclusive lease acquisition, expiry recovery, phase persistence, and safe progress logging in `src/event_platform/search/rebuild.py`.
- [X] T006 [P] [US1] Add lease/state tests in `tests/unit/test_search_rebuild.py`.

## Phase 4: User Story 2 - build and verify
- [X] T007 [US2] Implement target creation, live dual-write activation, chunked bulk indexing, bounded retries, reconciliation, and count/failure verification in `src/event_platform/search/rebuild.py`.
- [X] T008 [P] [US2] Add success, dual-write ordering, retry, failure, and verification tests in `tests/unit/test_search_rebuild.py` and `tests/failure/test_search_rebuild_failure.py`.

## Phase 5: User Story 3 - safe swap and retention
- [X] T009 [US3] Implement atomic alias swap, rollback retention metadata, failure-safe cleanup, and target deactivation in `src/event_platform/search/rebuild.py` and `src/event_platform/search/elasticsearch_rebuild.py`.
- [X] T010 [P] [US3] Add alias-safety and retention tests in `tests/unit/test_search_rebuild.py`.

## Phase 6: User Story 4 - status and CLI
- [X] T011 [US4] Add read-only rebuild status route and guarded CLI parser in `src/event_platform/api/routes/rebuild.py`, `src/event_platform/main.py`, and `src/event_platform/search/rebuild.py`.
- [X] T012 [P] [US4] Add status/CLI/OpenAPI tests in `tests/unit/test_search_rebuild.py`.
- [X] T013 [US4] Add service-gated real Mongo/Elasticsearch rebuild integration coverage in `tests/integration/test_rebuild_live.py`.

## Phase 7: Polish and quality gates
- [X] T014 Update architecture, traceability, AI workflow, and quickstart documentation.
- [X] T015 Run analyze, converge, staff/comprehensive review, remediation, and final quality gates; record the report under `specs/012-elasticsearch-online-rebuild/reviews/`.

## Dependencies

T001 precedes T002-T004. T002-T004 precede T005-T013. US1 precedes US2; US2 precedes US3; US4 is independently testable after the state port exists. T014-T015 follow implementation.
