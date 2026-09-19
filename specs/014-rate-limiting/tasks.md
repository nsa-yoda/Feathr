# Tasks: Mandatory Rate Limiting

**Input**: Design documents in `/specs/014-rate-limiting/`

## Phase 1: Setup

- [X] T001 Record accepted Feature 014 artifacts, route classes, identity rules, and bounded configuration decisions.
- [X] T002 [P] Add bounded rate-limit settings and Redis dependency wiring in `src/event_platform/core/settings.py` and `src/event_platform/main.py`.

## Phase 2: Foundational

- [X] T003 [P] Define route policy, decision, and injectable token math models in `src/event_platform/rate_limit/models.py`.
- [X] T004 [P] Implement direct-peer and trusted-proxy identity normalization in `src/event_platform/rate_limit/identity.py`.
- [X] T005 [P] Implement bounded monotonic local token bucket with idle/LRU eviction in `src/event_platform/rate_limit/local_bucket.py`.
- [X] T006 Implement Redis Lua token bucket adapter and classified failure boundary in `src/event_platform/rate_limit/redis_bucket.py`.
- [X] T007 Add unit tests for token math, identity normalization, route isolation, and local eviction in `tests/unit/test_rate_limit.py`.

## Phase 3: User Story 1 - Distributed route protection (P1)

- [X] T008 [US1] Implement route-class policy registry and safe bounded configuration in `src/event_platform/rate_limit/models.py`.
- [X] T009 [US1] Implement middleware route classification and request admission in `src/event_platform/api/middleware/rate_limit.py`.
- [X] T010 [US1] Add 429 problem response and `Retry-After`/`RateLimit-*` headers without key leakage.
- [X] T011 [US1] Add Redis integration coverage for atomic allow/deny/refill and independent route classes in `tests/integration/test_rate_limit_integration.py`.

## Phase 4: User Story 2 - Redis degraded fallback (P1)

- [X] T012 [US2] Wire Redis failure to the conservative local limiter and structured degraded event in middleware/lifecycle logging.
- [X] T013 [US2] Add failure tests for Redis outage, malformed script result, safe 429 contract, and bounded fallback state in `tests/failure/test_rate_limit_failure.py`.

## Phase 5: User Story 3 - Safe client identity (P1)

- [X] T014 [US3] Add route tests for spoofed forwarding headers, trusted-hop chains, malformed chains, IPv4/IPv6 normalization, and missing peer fallback.
- [X] T015 [US3] Document settings, route classes, identity trust model, degraded semantics, and reviewer quickstart in `docs/architecture/rate-limiting.md`, `docs/api-contract.md`, `ARCHITECTURE.md`, and traceability.

## Phase 6: Gates

- [X] T016 Run analyze, converge, staff review, comprehensive review, remediate findings, rerun repository gates, and record the final report.
