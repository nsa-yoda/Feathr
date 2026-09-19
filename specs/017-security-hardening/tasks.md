# Tasks: Security Hardening

**Input**: Design documents from `/specs/017-security-hardening/`
**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/security.md`

## Phase 1: Setup and foundational configuration

- [X] T001 Add bounded body, exact CORS origin, and dependency-timeout settings with validators in `src/event_platform/core/settings.py`.
- [X] T002 [P] Document security limits, trust boundaries, local Elasticsearch assumptions, and runtime image policy in `docs/architecture/security.md`, `docs/api-contract.md`, and `ARCHITECTURE.md`.
- [X] T003 [P] Add minimal non-root application and UI image definitions in `Dockerfile` and `frontend/Dockerfile`.

## Phase 2: User Story 1 — Bound hostile input

- [X] T004 [US1] Implement receive-time body-limit middleware with declared-length and streamed-byte enforcement in `src/event_platform/api/middleware/body_limit.py`.
- [X] T005 [US1] Integrate body-limit middleware into `src/event_platform/main.py` and preserve the problem/request-ID contract.
- [X] T006 [US1] Harden search/query character, cursor, date-range, and page-size validation and add dependency-call short-circuit tests.
- [X] T007 [US1] Add unit and failure coverage for oversized declared/streamed bodies, metadata abuse, query/cursor abuse, and safe 413/422 responses.

## Phase 3: User Story 2 — Browser and network trust

- [X] T008 [US2] Add exact-origin CORS configuration and explicit methods/headers without wildcard or credentials behavior.
- [X] T009 [US2] Add security-header middleware and verify headers on normal, validation, and dependency-error responses.
- [X] T010 [US2] Add forwarding-header spoof/trusted-chain regression coverage and document default proxy behavior.

## Phase 4: User Story 3 — Safe diagnostics and runtime privilege

- [X] T011 [US3] Apply bounded dependency operation timeouts and sanitize startup/configuration diagnostics.
- [X] T012 [US3] Add error-redaction and debug-disabled tests, including sentinel secrets and raw driver messages.
- [X] T013 [US3] Add static checks for non-root application/UI container users and local-only Elasticsearch security documentation.

## Phase 5: Polish and acceptance

- [X] T014 [P] Update requirements traceability and AI workflow records with decisions, corrections, and evidence.
- [X] T015 Run analyze, converge, staff review, comprehensive review, targeted remediation, and all repository gates; record the final review report.

## Dependencies & Execution Order

- Phase 1 blocks all user stories.
- User Story 1 establishes request bounds before User Story 2 and 3 integration tests.
- User Story 2 and User Story 3 may proceed in parallel after foundational configuration.
- Phase 5 follows all implementation and regression tests.
