# Tasks: Integration Test Lifecycles

**Input**: Design documents from `/specs/019-integration-test-lifecycles/`
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/integration-harness.md`

## Phase 1: Setup and harness foundation

- [X] T001 Record the current integration-test collection, environment variables, skip behavior, and existing fixed-sleep/polling sites in `CODEX_WORK.LOG` and `tests/integration/README.md`.
- [X] T002 [P] Add the shared namespace, endpoint capability, safe diagnostics, and bounded `poll_until` helpers in `tests/integration/support.py`.
- [X] T003 [P] Add the Feature 019 focused integration command, required endpoint documentation, and cleanup/skip contract to `tests/integration/README.md`, `specs/019-integration-test-lifecycles/quickstart.md`, `README.md`, and `docs/testing-strategy.md`.

## Phase 2: Application lifecycle wiring

- [X] T004 [US1] Add the configured `ElasticsearchSearchService` assignment to `app.state.search_service` in `src/event_platform/main.py` and remove it deterministically during lifespan shutdown.
- [X] T005 [US2] Add unit coverage in `tests/unit/test_app_lifecycle.py` or `tests/unit/test_search.py` proving configured search service ownership and unavailable-service cleanup without opening clients at import time.

## Phase 3: User Story 1 — canonical ingestion and query

- [X] T006 [P] [US1] Add a real-service app fixture in `tests/integration/test_integration_lifecycles.py` that configures unique Mongo database/collection settings and uses `TestClient` lifespan ownership.
- [X] T007 [US1] Add the real `POST /events` -> persistence worker -> `GET /events` lifecycle assertion in `tests/integration/test_integration_lifecycles.py` with bounded polling and canonical payload checks.
- [X] T008 [US1] Add the real duplicate/redelivery lifecycle assertion in `tests/integration/test_integration_lifecycles.py` or the existing worker integration module, proving one Mongo document and safe duplicate metrics.

## Phase 4: User Story 2 — change-stream search

- [X] T009 [US2] Add the real Mongo replica-set change-stream -> Elasticsearch alias -> HTTP search lifecycle assertion in `tests/integration/test_integration_lifecycles.py` with bounded search polling and isolated checkpoint/index cleanup.
- [X] T010 [US2] Replace fixed synchronization sleeps in `tests/integration/test_search_projection_integration.py` with the shared bounded poll helper and safe timeout diagnostics.

## Phase 5: User Story 3 — analytics and realtime cache

- [X] T011 [P] [US3] Add a real HTTP analytics lifecycle assertion for seeded types/times and inclusive UTC grouping in `tests/integration/test_integration_lifecycles.py` or `tests/integration/test_mongodb_analytics_integration.py`.
- [X] T012 [P] [US3] Add a real HTTP realtime cache miss/hit lifecycle assertion with logical result equality, TTL bounds, and Redis namespace cleanup in `tests/integration/test_integration_lifecycles.py` or `tests/integration/test_realtime_stats_integration.py`.

## Phase 6: User Story 4 — rebuild and live continuity

- [X] T013 [US4] Extend `tests/integration/test_rebuild_live.py` to add a live projected event after rebuild activation and prove prior plus live metadata remain searchable through the serving alias.
- [X] T014 [US4] Add bounded polling and cleanup diagnostics to the rebuild/projection integration paths without exposing dependency credentials or complete event metadata.

## Phase 7: Acceptance and evidence

- [X] T015 [US1] [US2] [US3] [US4] Run the Feature 019 focused integration selection, verify collection and explicit service-gated skip behavior, and record service-backed execution limits; when endpoints are available, the scenarios use real clients, unique namespaces, bounded polling, and `finally` cleanup.
- [X] T016 [P] Reconcile `docs/requirements-traceability.md`, `docs/ai-workflow-log.md`, `README.md`, `docs/testing-strategy.md`, and the Feature 019 quickstart with exact test counts, skip semantics, and service-gated limits.
- [X] T017 Run `speckit-analyze`, `speckit-converge`, staff review, comprehensive review, targeted remediation, and all repository gates; record the final review report and timestamped work log.

## Dependencies & Execution Order

- Phase 1 precedes all lifecycle tests.
- T004 and T005 precede app-level scenarios T006-T009.
- T010 can proceed with T011-T014 after T002.
- T015-T017 follow all scenario work and any convergence tasks.

## Implementation Strategy

1. Establish the bounded harness and app search-service wiring.
2. Deliver the canonical ingestion/query and change-stream search P1 scenarios.
3. Add analytics/cache and rebuild continuity scenarios.
4. Reconcile evidence and run full review gates.
