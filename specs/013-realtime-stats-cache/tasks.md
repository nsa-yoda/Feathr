# Tasks: Realtime Statistics Cache

**Input**: Design documents from `specs/013-realtime-stats-cache/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/realtime-stats.md

## Phase 1: Setup

- [X] T001 Record accepted Feature 013 Spec Kit artifacts, architecture decisions, and bounded window/TTL defaults.
- [X] T002 Add the async Redis dependency and lockfile update.

## Phase 2: Foundational

- [X] T003 Add bounded Redis/cache settings to `src/event_platform/core/settings.py`.
- [X] T004 Add optional async Redis client creation/closure to `src/event_platform/main.py` without making Redis startup mandatory.
- [X] T005 Define typed realtime response, cache port, safe cache failure classification, and deterministic serialization in `src/event_platform/cache/realtime.py`.

## Phase 3: User Story 1 - Rolling Summary (P1)

- [X] T006 [US1] Implement bounded inclusive rolling-window Mongo aggregation and typed result computation in `src/event_platform/cache/realtime.py`.
- [X] T007 [US1] Implement `GET /events/stats/realtime` validation, response headers, request ID, safe 422/503 behavior, and app wiring in `src/event_platform/api/routes/realtime_stats.py` and `src/event_platform/main.py`.
- [X] T008 [US1] Add unit coverage for default/explicit windows, inclusive bounds, empty results, invalid windows, deterministic counts, and cache key identity in `tests/unit/test_realtime_stats.py`.

## Phase 4: User Story 2 - Cache Reuse (P1)

- [X] T009 [US2] Implement Redis cache-aside hit/miss/TTL write and malformed-payload handling with configurable default TTL.
- [X] T010 [US2] Add deterministic single-flight coalescing for concurrent misses without unbounded state.
- [X] T011 [US2] Add unit tests for miss then hit, TTL propagation, expiration/malformed payload misses, and concurrent coalescing.

## Phase 5: User Story 3 - Redis Degraded Path (P1)

- [X] T012 [US3] Translate Redis read/write/serialization failures to `BYPASS`, structured cache degradation logs, and successful Mongo responses.
- [X] T013 [US3] Add failure tests for Redis unavailable, Mongo unavailable, safe problem details, and no secret/key leakage.
- [X] T014 [US3] Add real Mongo/Redis integration lifecycle coverage in `tests/integration/test_realtime_stats_integration.py`.

## Phase 6: Documentation and Gates

- [X] T015 Update API contract, architecture, traceability, AI workflow, and quickstart documentation with exact cache semantics.
- [X] T016 Run analyze, converge, staff review, comprehensive review, remediate findings, rerun gates, and record the final report.
