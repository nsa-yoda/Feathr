# Quickstart Validation: Platform Foundation

Run these checks after Feature 001 is implemented. This guide validates observable behavior; [the HTTP contract](contracts/http-foundation.md) defines response fields and [the data model](data-model.md) defines settings and lifecycle semantics.

## Prerequisites

- Python 3.12 or newer and `uv` installed.
- Repository root as the working directory.
- Port 8000 available locally.
- No MongoDB, Elasticsearch, or Redis service is required for this foundation slice.

## Install and check

```bash
uv sync --locked
make format-check
make lint
make typecheck
make test-unit
```

Expected: the lock agrees with `pyproject.toml`, all checks pass, and unit tests verify settings, lifespan, import behavior, and problem responses. Pytest registers `unit`, `integration`, and `failure` markers; real-service integration and failure suites are added by later features.

## Start and inspect the base service

In one terminal:

```bash
uv run --locked uvicorn event_platform.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

In another terminal:

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/openapi.json
curl -i http://127.0.0.1:8000/missing
```

Expected: liveness returns `200` and `{"status":"alive"}`; OpenAPI returns `200`; the missing route returns `404` with `application/problem+json`, the seven contract members, and matching `X-Request-ID`. Stop the server with Ctrl-C; it exits cleanly.

## Reject invalid settings

With no server already using port 8000:

```bash
EVENT_PLATFORM_LOG_LEVEL=LOUD uv run --locked uvicorn event_platform.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Expected: startup exits unsuccessfully before serving traffic. The diagnostic identifies `EVENT_PLATFORM_LOG_LEVEL` or its `log_level` field and does not echo the supplied value. The same rule applies to malformed future secret settings.

## Scope of this validation

This guide proves the foundation's startup, shutdown, configuration, API description, liveness, and error shape. The repository-wide Compose, Postman, real-dependency integration, and failure checks become runnable as their owning features land.
