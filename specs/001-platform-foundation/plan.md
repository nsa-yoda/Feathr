# Implementation Plan: Platform Foundation

**Branch**: `main` (active Spec Kit feature: `001-platform-foundation`) | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

**Input**: `specs/001-platform-foundation/spec.md`; governing constraints come from `.specify/memory/constitution.md`, `CODEX-HANDOFF.md`, and accepted ADRs.

## Summary

Establish a Python service skeleton that starts and stops cleanly, exposes OpenAPI and minimal liveness, validates runtime settings, and returns one safe RFC 9457-style error shape. Use the locked FastAPI/Pydantic stack, a `src/` package layout aligned with existing package placeholders, and lifespan ownership for future async clients. Define quality commands and focused tests now, while leaving business behavior and dependency integrations to later features.

## Technical Context

**Language/Version**: Python 3.12+.

**Primary Dependencies**: FastAPI, Pydantic v2, pydantic-settings, Uvicorn; `uv` for locked dependency management. Keep the foundation dependency set small; add async Mongo, Elasticsearch, and Redis clients in their owning features.

**Storage**: None in Feature 001. MongoDB remains the future canonical store; Elasticsearch and Redis remain derived/non-authoritative per the locked architecture.

**Testing**: pytest and pytest-asyncio; lifespan-aware TestClient for HTTP checks; a bounded process-level smoke test for the documented start/stop path; Ruff formatting/lint; and mypy typing. Unit tests cover configuration, app lifespan, import side effects, request-ID propagation on successful and error responses, and problem responses. The repository also exposes `make test-integration` and `make test-failure` category commands that select the registered markers and pass while those directories contain no later-feature tests; the owning features add the real-service cases.

**Target Platform**: macOS developer environment and Linux container runtime; ASGI service runs as one process in the demo.

**Project Type**: Async HTTP web service.

**Performance Goals**: No throughput target for the empty service. Startup/liveness/shutdown must complete within bounded local smoke-test timeouts; later endpoint features define workload targets.

**Constraints**: No external dependency required for foundation startup; no network client at import time; no blocking network I/O in async handlers; safe error details and secret handling; future dependency clients owned by lifespan; no extra queue or service process.

**Scale/Scope**: One base application process, one liveness endpoint, default OpenAPI/docs, central problem mapping, typed settings, package boundaries, and local quality checks. No event endpoints or datastore adapters in this slice.

## Constitution Check

*GATE: Passed before Phase 0 research; re-evaluated after Phase 1 design below.*

| Governing requirement | Plan response | Gate |
|---|---|---|
| I, III: canonical versus derived stores; avoid false guarantees | Feature 001 adds no storage or event processing; package boundaries reserve the locked Mongo/ES/Redis roles. | PASS |
| II, V, IX: explicit queue semantics, rate limiting, and spec-first delivery | No ingestion route exists in this feature. Queue and rate-limit packages remain boundaries for later specified features; this spec and plan precede implementation. | PASS |
| IV, VII: failures and observable operations | Central safe problems, structured foundation lifecycle/error logs, and startup errors are specified; full metrics/component health remain in Feature 015. The failure-test command is category plumbing only until later dependency features add failure cases. | PASS |
| V: security and privacy | No credentials in defaults, startup diagnostics, or HTTP problems; no request-body logging; no forwarded-IP handling in this feature. | PASS |
| VI: async and lifecycle ownership | App factory/lifespan owns future clients; foundation startup creates none; async routes avoid blocking I/O. | PASS |
| VIII: meaningful tests | Settings, lifespan, process start/stop, successful/error request IDs, error mapping, and import effects have focused unit/smoke coverage; real-service tests start with integration features. | PASS |
| X, XI: reviewer experience and simplicity | OpenAPI and liveness support review, with small explicit modules and no ceremonial ports. | PASS |

The plan preserves ADR 0001 (FastAPI), ADR 0012 (single process), ADR 0013 (problem errors), and ADR 0014 (health semantics). No constitutional exception or ADR supersession is needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-platform-foundation/
├── REQUEST.md
├── spec.md
├── checklists/requirements.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/http-foundation.md
```

Repository-level acceptance evidence also updates `README.md`, `docs/api-contract.md`, `docs/requirements-traceability.md`, `docs/ai-workflow-log.md`, and `CODEX_WORK.LOG`. The process smoke path uses `src/event_platform/core/uvicorn_logging.json` so Uvicorn lifecycle and access records share the service JSON schema.

`tasks.md` contains the dependency-ordered implementation and acceptance tasks generated from these artifacts.

### Source Code (repository root)

```text
pyproject.toml
uv.lock
Makefile
src/event_platform/
├── __init__.py
├── main.py                 # create_app ASGI factory
├── core/
│   ├── logging.py          # structured runtime and access logging
│   ├── settings.py         # validated configuration
│   └── uvicorn_logging.json # pre-lifespan Uvicorn logging configuration
├── api/
│   ├── problems.py         # problem model and exception mapping
│   ├── middleware/         # request ID assignment
│   └── routes/
│       └── health.py       # minimal liveness only
├── domain/
├── queue/
├── storage/
├── search/
├── cache/
├── rate_limit/
├── worker/                       # persistence worker orchestration
└── observability/
tests/
├── unit/                   # settings, lifespan, problems, import effects
├── integration/            # reserved for real-service features
└── failure/                # reserved for failure features
```

**Structure Decision**: Extend the repository's concrete `src/event_platform` boundaries. `api` owns HTTP concerns, `core` owns settings, composition, lifecycle, and Uvicorn JSON logging, `domain` owns contracts, and executable worker orchestration lives in singular `worker/` while search projection orchestration remains under `search/`. Queue, storage, search, cache, and rate-limit packages are boundaries only in this feature; avoid premature interfaces or client creation. `main.py` supplies a no-argument app factory loaded with `uvicorn --factory`; settings are validated during lifespan startup or explicitly injected by tests. Minimal request ID middleware sets request state and response header; Feature 015 expands observability without changing the public error shape. The Makefile exposes the four foundation quality checks plus no-op-safe integration and failure category commands so later feature suites have stable entrypoints.

## Phase 0 Research Decisions

See [research.md](research.md) for dependency, lifespan, settings, error, and test-tool decisions with alternatives. No `NEEDS CLARIFICATION` item remains.

## Phase 1 Design Decisions

See [data-model.md](data-model.md) for configuration, request context, problem response, and lifecycle state; [contracts/http-foundation.md](contracts/http-foundation.md) for the external HTTP shape; and [quickstart.md](quickstart.md) for runnable validation.

## Post-Design Constitution Recheck

**PASS.** The design adds only typed in-process state and one liveness route. It creates no dependency client, background worker, durable-acceptance claim, alternate source of truth, or new infrastructure. Error details remain safe, request IDs are returned to every HTTP response, structured foundation lifecycle/error logs are emitted, and focused tests cover process startup/shutdown, invalid settings, import safety, and problem mapping. The integration/failure command entrypoints do not imply that real dependency coverage exists in this feature. Feature 015 retains ownership of readiness, component health, and metrics.

## Complexity Tracking

No constitutional violations require a complexity exception.
