# Phase 0 Research: Platform Foundation

**Date**: 2026-09-18
**Scope**: Resolve Feature 001 tooling, lifecycle, configuration, and HTTP error choices under the locked architecture.

## Dependency and lock workflow

**Decision**: Define the package in `pyproject.toml` with `requires-python = ">=3.12"`, keep runtime and development dependencies separate, commit `uv.lock`, and use `uv sync --locked` or `uv run --locked` for verification. Runtime deployment can omit the development group.

**Rationale**: The project request prefers uv and requires repeatable resolution. `--locked` checks that the lock and manifest agree, which makes a stale lock visible during checks.

**Alternatives considered**: Unlocked `pip install` cannot reproduce the resolved set. `uv --frozen` reads the lock without checking whether it matches the manifest, so it is weaker for quality gates. Poetry or pip-tools would add a second package workflow without a project need.

**Sources**: [uv project configuration](https://docs.astral.sh/uv/concepts/projects/config/), [uv layout](https://docs.astral.sh/uv/concepts/projects/layout/), [uv synchronization](https://docs.astral.sh/uv/concepts/projects/sync/).

## App factory and lifecycle

**Decision**: Export `create_app()` from `event_platform.main` and run `uvicorn event_platform.main:create_app --factory`. Use FastAPI's async lifespan context to validate settings and own later clients/tasks. Feature 001's lifespan opens no external clients. Tests can inject settings into the factory, enter lifespan with `TestClient` as a context manager, and assert clean exit.

**Rationale**: A factory keeps tests isolated and avoids import-time client construction. FastAPI lifespan has a defined before-serving and after-shutdown boundary. The single process remains mandatory while the queue is in-process.

**Alternatives considered**: A module-level app instance may encourage import-time setup; deprecated startup/shutdown events would split lifecycle ownership. Multiple Uvicorn workers violate the local queue design. An `httpx.ASGITransport` client alone does not invoke lifespan.

**Sources**: [Uvicorn factory setting](https://www.uvicorn.org/settings/), [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [Starlette lifespan](https://www.starlette.io/lifespan/), [FastAPI testing events](https://fastapi.tiangolo.com/advanced/testing-events/), [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/).

## Typed environment settings and safe failures

**Decision**: Use `pydantic-settings` `BaseSettings` with `EVENT_PLATFORM_` prefix, explicit typed defaults for foundation-only fields, and validation on lifespan startup. Start with environment (`local|test|production`) and log level. Keep integration-specific secrets/settings in their later owning features; use `SecretStr` where applicable. Configure `hide_input_in_errors=True` and produce a sanitized startup diagnostic that names the invalid field without echoing its value.

**Rationale**: Pydantic Settings validates environment-derived values and defaults; explicit types prevent silent fallback. Secret wrappers protect ordinary representations, while a deliberately sanitized diagnostic protects the startup error path.

**Alternatives considered**: Ad hoc `os.environ` parsing scatters validation. Loading settings at import time makes imports environment-dependent. Requiring Mongo/ES/Redis URLs before those integrations exist would make the base app fail its standalone acceptance scenario.

**Sources**: [Pydantic Settings concepts](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), [Pydantic error input hiding](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.hide_input_in_errors), [Pydantic SecretStr](https://docs.pydantic.dev/latest/api/types/#pydantic.types.SecretStr).

## Problem responses and request IDs

**Decision**: Use one serializer for `application/problem+json` with RFC 9457 members `type`, `title`, `status`, `detail`, `instance`, plus project extensions `error_code` and `request_id` from `docs/api-contract.md`. For the generic foundation problems, use `about:blank`, standard status titles, and stable codes `route_not_found`, `request_validation_failed`, and `internal_error`. Generate a server-owned request ID per request and return it in `X-Request-ID` and the problem body. Install handlers for Starlette `HTTPException`, FastAPI `RequestValidationError`, and unexpected `Exception`; keep unexpected details generic and debug tracebacks disabled. Explicitly document problem responses in generated OpenAPI where routes declare them.

**Rationale**: RFC 9457 allows extension members and requires `application/problem+json`. Starlette's HTTP exception handler covers framework-generated 404 as well as application HTTP errors. Runtime exception handlers alone do not correct OpenAPI's default validation response schema.

**Alternatives considered**: Default FastAPI errors use a different shape. Catching only FastAPI's `HTTPException` misses framework-generated errors. A project-specific problem type URL would be premature without a stable published documentation host; `about:blank` fits generic status problems.

**Sources**: [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html), [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/), [Starlette exceptions](https://www.starlette.io/exceptions/), [FastAPI additional responses](https://fastapi.tiangolo.com/advanced/additional-responses/).

## Quality and test tooling

**Decision**: Configure Ruff format/check, mypy strict mode for the application package, pytest with registered `unit`, `integration`, and `failure` markers and strict marker validation, and pytest-asyncio with explicit function loop scope. Keep tests focused on configuration, lifespan, import effects, and error contracts. Use `TestClient` in a context manager for lifespan; disable test-client exception re-raising only in the intentional unexpected-error case.

**Rationale**: The checks are available before later code grows. Explicit markers and loop scope prevent test classification and async fixture behavior from drifting. Locking the tool versions makes repeated checks comparable.

**Alternatives considered**: Running no checks until Feature 024 would defer quality defects. Full real-service integration testing has no subject in the foundation slice and belongs to features that introduce those services. An arbitrary coverage target would not prove the intended semantics.

**Sources**: [Ruff formatter](https://docs.astral.sh/ruff/formatter/), [Ruff Python target](https://docs.astral.sh/ruff/settings/#target-version), [mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html), [Pydantic mypy plugin](https://docs.pydantic.dev/latest/integrations/mypy/), [pytest configuration](https://docs.pytest.org/en/stable/reference/customize.html), [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html), [pytest-asyncio configuration](https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html), [Starlette TestClient](https://www.starlette.io/testclient/).

## Clarification disposition

The request, constitution, accepted ADRs, and Feature 001 specification settle all guarantee-affecting choices for this phase. Exact patch versions are selected by the lockfile during implementation; they do not change this design. No `NEEDS CLARIFICATION` item remains.
