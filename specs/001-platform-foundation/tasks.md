---
description: "Dependency-ordered implementation tasks for Platform Foundation"
---

# Tasks: Platform Foundation

**Input**: `specs/001-platform-foundation/spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/http-foundation.md`, and `quickstart.md`.

**Tests**: Required by the Feature 001 request and spec. Write story tests before their implementation, then run the focused suite again at each story checkpoint.

**Organization**: Tasks are grouped by the three prioritized user stories. Package/tooling work shared by all stories is in Setup and Foundational phases.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: This task can run in parallel with other currently ready tasks because it edits different files and has no unmet dependency.
- **[USn]**: The task belongs to the matching user story in `spec.md`.
- All paths are relative to the repository root.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the reproducible Python package and the empty ownership boundaries needed by every story.

- [X] T001 Define the Python 3.12+ `src` package, FastAPI/Pydantic Settings/Uvicorn runtime dependencies, and uv development dependencies in `pyproject.toml` per `research.md`.
- [X] T002 Resolve and write the dependency lock in `uv.lock`, then confirm `uv sync --locked` accepts `pyproject.toml` and `uv.lock` together (depends on T001).
- [X] T003 [P] Add package markers in `src/event_platform/__init__.py`, `src/event_platform/core/__init__.py`, `src/event_platform/api/__init__.py`, `src/event_platform/api/routes/__init__.py`, and `src/event_platform/api/middleware/__init__.py`.
- [X] T004 [P] Add empty ownership package markers in `src/event_platform/application/__init__.py`, `src/event_platform/domain/__init__.py`, `src/event_platform/queue/__init__.py`, `src/event_platform/storage/__init__.py`, `src/event_platform/search/__init__.py`, `src/event_platform/cache/__init__.py`, `src/event_platform/rate_limit/__init__.py`, `src/event_platform/workers/__init__.py`, and `src/event_platform/observability/__init__.py`; do not introduce adapters or clients.

**Checkpoint**: The locked package installs and all planned import boundaries exist without business behavior.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish a shared test/quality baseline and the app factory that each story extends. Complete this phase before any story work.

- [X] T005 [P] Configure Ruff format/check, strict mypy, pytest strict markers (`unit`, `integration`, `failure`), and pytest-asyncio function loop scope in `pyproject.toml` (depends on T001).
- [X] T006 [P] Create a no-argument `create_app()` and async lifespan skeleton in `src/event_platform/main.py`, with debug traceback behavior disabled and no import-time network clients or tasks (depends on T003).
- [X] T007 Add `format-check`, `lint`, `typecheck`, and `test-unit` targets that use the locked environment in `Makefile`; point the unit target at `tests/unit/` (depends on T002 and T005).

**Checkpoint**: The app factory is importable and the foundation checks are callable; integration and failure test categories are registered for their later owning features.

---

## Phase 3: User Story 1 - Start and stop the base service (Priority: P1) 🎯 MVP

**Goal**: A reviewer can start the base process, use `/health/live`, `/openapi.json`, and `/docs`, then shut it down cleanly without external services.

**Independent Test**: Enter the app lifespan, request the three documented surfaces, assert liveness is `{"status":"alive"}`, exit lifespan, and confirm no startup-owned resource remains.

### Tests for User Story 1

- [X] T008 [P] [US1] Write the lifecycle/HTTP tests in `tests/unit/test_app_lifecycle.py` for factory startup, `/health/live`, `/openapi.json`, `/docs`, and clean context exit; run the focused tests and observe the missing-route failure before implementation.
- [X] T009 [P] [US1] Add an import-safety test in `tests/unit/test_import_safety.py` that imports the foundation package and detects network client creation, socket connections, or background-task scheduling during import; run it with T008 and retain it for the final full-module pass.

### Implementation for User Story 1

- [X] T010 [US1] Implement only the minimal `GET /health/live` response in `src/event_platform/api/routes/health.py`, keeping it distinct from future readiness and component health (depends on T008).
- [X] T011 [US1] Register the health router and complete the clean startup/shutdown path in `src/event_platform/main.py`; keep OpenAPI/docs available and use one process with no dependency clients (depends on T010).

**Checkpoint**: US1 tests pass without MongoDB, Elasticsearch, Redis, or a queue service; the documented base-service smoke path is usable.

---

## Phase 4: User Story 2 - Diagnose invalid configuration (Priority: P2)

**Goal**: Typed defaults allow foundation startup, while invalid settings fail before traffic with a diagnostic that names the field but omits the supplied value.

**Independent Test**: Start the app with defaults and injected valid settings, then attempt startup with an invalid environment or log level and inspect the sanitized failure.

### Tests for User Story 2

- [X] T012 [P] [US2] Write settings tests in `tests/unit/test_settings.py` for valid defaults, accepted environment/log levels, invalid values, and diagnostic redaction; run them before implementing `src/event_platform/core/settings.py`.
- [X] T013 [P] [US2] Write lifespan startup tests in `tests/unit/test_app_settings.py` proving invalid settings fail before serving, valid settings are app-owned, and no Mongo/ES/Redis credentials are required; run them before app integration.

### Implementation for User Story 2

- [X] T014 [P] [US2] Implement `ServiceSettings`, `EVENT_PLATFORM_` environment loading, typed validation, and sanitized startup error classification in `src/event_platform/core/settings.py` per `data-model.md` (depends on T012).
- [X] T015 [P] [US2] Document only the foundation environment and log-level defaults, with no committed credentials, in `.env.example` per `data-model.md` (depends on T012).
- [X] T016 [US2] Validate/inject settings during the lifespan in `src/event_platform/main.py`, store one app-owned settings object, and fail startup before serving on invalid values (depends on T013 and T014).

**Checkpoint**: US2 settings and startup tests pass independently of later external integrations; US1 still passes.

---

## Phase 5: User Story 3 - Receive a consistent error response (Priority: P3)

**Goal**: API errors use one safe `application/problem+json` shape with stable codes, matching HTTP status, and a server-owned request ID.

**Independent Test**: Request an unknown route and use test-only typed/failing routes for validation and unexpected errors; assert all seven fields, media type, status/header agreement, redaction, and declared OpenAPI problem schema.

### Tests for User Story 3

- [X] T017 [P] [US3] Write problem contract tests in `tests/unit/test_problems.py` for 404, 405 with `Allow`, test-only 422, test-only 500, safe details, seven fields, matching status, and OpenAPI problem declarations; run them before handlers exist.
- [X] T018 [P] [US3] Write request-ID tests in `tests/unit/test_request_id.py` for one generated UUID per request, matching `X-Request-ID`/problem body, and non-trust of an inbound header; run them before middleware exists.

### Implementation for User Story 3

- [X] T019 [P] [US3] Implement the typed problem model/serializer and handlers for Starlette HTTP errors, FastAPI validation errors, and unexpected errors in `src/event_platform/api/problems.py`, preserving required HTTP headers (depends on T017).
- [X] T020 [P] [US3] Implement request-context assignment and `X-Request-ID` propagation in `src/event_platform/api/middleware/request_id.py`, without logging request bodies or accepting caller IDs (depends on T018).
- [X] T021 [US3] Register problem handlers and request-ID middleware in `src/event_platform/main.py`, and declare applicable problem responses on `src/event_platform/api/routes/health.py` so OpenAPI matches runtime behavior (depends on T019 and T020).

**Checkpoint**: US3 error and request-ID tests pass; US1 and US2 regressions remain green.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Reconcile reviewer documentation, traceability, requirements checks, and final Feature 001 evidence.

- [X] T022 [P] Document the actual start/stop command, settings defaults, four foundation quality commands, and liveness scope in `README.md` after the story implementation is stable.
- [X] T023 [P] Reconcile `docs/api-contract.md` with the implemented `/health/live`, `X-Request-ID`, and seven-field problem behavior without claiming later endpoints exist.
- [X] T024 [P] Replace unresolved Feature 001 evidence cells with concrete source and test references in `docs/requirements-traceability.md`, leaving unrelated feature rows untouched.
- [X] T025 Append factual Feature 001 AI contributions and corrections to `docs/ai-workflow-log.md`, and append timestamped findings/status to `CODEX_WORK.LOG` as requested by the user.
- [X] T026 Re-evaluate `specs/001-platform-foundation/checklists/requirements.md` and `specs/001-platform-foundation/checklists/foundation.md` against the implemented scope; resolve any requirements gap in the affected `spec.md`, `plan.md`, or `contracts/http-foundation.md` before acceptance.
- [X] T027 Run `make format-check`, `make lint`, `make typecheck`, `make test-unit`, and the scenarios in `specs/001-platform-foundation/quickstart.md`; record exact results, limitations, and deferred real-service suites in `CODEX_WORK.LOG`.

**Checkpoint**: Feature 001 artifacts and implementation agree. Continue with `$speckit-analyze`, `$speckit-implement`, convergence, and the review gates in `CODEX-HANDOFF.md` at their prescribed workflow stages.

---

## Dependencies & Execution Order

### Phase Dependencies

1. Setup T001-T004 precedes Foundational. T002 depends on T001; T003 and T004 can proceed alongside dependency resolution.
2. Foundational T005-T007 precedes every user story. T005 and T006 can proceed in parallel after their setup dependencies; T007 follows T005 and the lockfile.
3. US1 follows Foundational and produces the app route/factory baseline. US2 and US3 each use that baseline but have no dependency on each other.
4. Polish follows all three story checkpoints. Its independent documentation edits can proceed in parallel; final checklist review and validation follow them.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational; delivers the MVP base service.
- **US2 (P2)**: Starts after US1's app factory/route baseline. Its settings model/tests are isolated; `main.py` lifespan wiring is serialized with other `main.py` edits.
- **US3 (P3)**: Starts after US1's baseline. Its problem and middleware modules/tests are isolated from US2; `main.py` registration is serialized with US2 wiring.

### Within Each User Story

- Write and run the story tests first; observe a failure for the missing story behavior before implementing it.
- Implement typed models/handlers before app wiring, then rerun that story and earlier-story tests.
- Do not mark a story complete until its independent test criterion and applicable error path pass.

### Parallel Opportunities

- T003 and T004 touch separate package marker files.
- T005 and T006 touch `pyproject.toml` and `src/event_platform/main.py` respectively.
- T008/T009, T012/T013, and T017/T018 are independent test-file pairs within their stories.
- T014/T015 and T019/T020 are separate implementation-file pairs after the tests for their stories exist.
- T022/T023/T024 touch separate documentation files after story implementation.

## Parallel Execution Examples

### User Story 1

```text
T008 tests/unit/test_app_lifecycle.py  ||  T009 tests/unit/test_import_safety.py
then T010 src/event_platform/api/routes/health.py -> T011 src/event_platform/main.py
```

### User Story 2

```text
T012 tests/unit/test_settings.py  ||  T013 tests/unit/test_app_settings.py
then T014 src/event_platform/core/settings.py  ||  T015 .env.example
then T016 src/event_platform/main.py
```

### User Story 3

```text
T017 tests/unit/test_problems.py  ||  T018 tests/unit/test_request_id.py
then T019 src/event_platform/api/problems.py  ||  T020 src/event_platform/api/middleware/request_id.py
then T021 src/event_platform/main.py and src/event_platform/api/routes/health.py
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational tasks.
2. Complete US1 tests, route, and app registration.
3. Run the US1 independent test criterion and demonstrate the base service using `specs/001-platform-foundation/quickstart.md`.

### Incremental Delivery

1. Add US2 typed configuration and fail-fast startup, preserving US1 behavior.
2. Add US3 problem mapping and request IDs, preserving US1/US2 behavior.
3. Finish documentation, checklists, traceability, and the applicable Feature 001 quality gates.

### Acceptance Boundaries

- The test markers and directories for real-service integration/failure coverage are created now; those suites and their `make test-integration`/`make test-failure` gates become meaningful when later features introduce MongoDB, Elasticsearch, Redis, and failure paths. Record them as deferred for Feature 001 rather than reporting an empty suite as passing.
- The mandatory staff and full review extensions are separate workflow gates. The earlier bootstrap attempt could not download them because GitHub DNS resolution failed; retry their installation before those review stages, without changing Feature 001's runtime scope.
- The user authorized commits during implementation. Stage verified Feature 001 work selectively; no push was requested.
