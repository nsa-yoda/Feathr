# Distributed Event Processing Platform

> **Current state:** Feature 001 provides the runnable platform foundation. Event ingestion, data services, reviewer UI, and Compose are planned in later features; see `CODEX-HANDOFF.md` and the active Spec Kit artifacts.

A production-oriented event ingestion, processing, search, analytics, caching, and reviewer-demo platform built with FastAPI, MongoDB, Elasticsearch, Redis, and an assessment-mandated in-process SQS-style queue.

## Run the foundation service

Use Python 3.12 or newer and `uv`. From the repository root:

```bash
cp .env.example .env
uv sync --locked
uv run --locked uvicorn event_platform.main:create_app --factory --log-config src/event_platform/core/uvicorn_logging.json --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/docs` for API discovery or request `http://127.0.0.1:8000/health/live` for liveness. Stop the foreground server with Ctrl-C. Liveness returns `{"status":"alive"}` and proves only that the base process responds; it does not check MongoDB, Elasticsearch, Redis, or a queue. Those services are not needed to run Feature 001.

| Variable | Default | Allowed values | Purpose |
|---|---|---|---|
| `EVENT_PLATFORM_ENV` | `local` | `local`, `test`, `production` | Runtime environment label. |
| `EVENT_PLATFORM_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Foundation log-level setting. |

An invalid foundation setting aborts startup before serving. The diagnostic names the field without printing its supplied value. Later feature settings will be documented as those integrations land.

Run the foundation checks with:

```bash
make format-check
make lint
make typecheck
make test-unit
make test-integration
make test-failure
```

The unit suite covers settings, lifespan, import safety, request IDs, and problem responses. The current HTTP contract is in [the foundation contract](specs/001-platform-foundation/contracts/http-foundation.md), and its manual check is in [the quickstart validation](specs/001-platform-foundation/quickstart.md). The integration and failure commands are empty-safe until later features add real-service cases.

## Target reviewer quick start after later features

The finished repository must support a workflow no more complicated than:

```bash
cp .env.example .env
docker compose up --build
```

The completed submission README must then list:

- Demo UI URL
- FastAPI/OpenAPI URL
- health URLs
- Prometheus metrics URL
- Postman import/run instructions
- unit/integration/failure test commands

## Required final sections

Codex must replace this planning README with a complete submission README containing:

1. Project overview and key guarantees
2. Architecture summary and link to `ARCHITECTURE.md`
3. Quick start / Docker Compose
4. Configuration table
5. API endpoint documentation with examples
6. Queue semantics and `202` durability caveat
7. Testing philosophy and commands
8. Postman reviewer workflow
9. Demo UI guide
10. Operational/health/metrics guide
11. Elasticsearch rebuild command/behavior
12. SQS production migration summary
13. Known constraints/tradeoffs
14. **AI in My Workflow** — tools used, concrete contributions, corrections/pushback, and how AI changed speed/quality, grounded in `docs/ai-workflow-log.md`

Do not leave generic AI boilerplate. The panel specifically wants evidence of strategic AI use and human judgment.
