# Distributed Event Processing Platform

> **Current state:** Features 001-021 provide the API, data services, lifecycle controls, failure coverage, and reviewer Docker Compose configuration. Static Compose validation is complete; live startup and smoke require a running Docker daemon. The full reviewer UI and Postman workflow are delivered by later features; see `CODEX-HANDOFF.md` and the active Spec Kit artifacts.

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
make coverage
```

The unit suite is the isolated semantic suite for settings, lifecycle, queue/worker state, query/search/analytics contracts, caching, rate limiting, request IDs, and problem responses. `make coverage` measures executed source lines and branches and writes `coverage/coverage.xml`; it is a signal, not proof of semantic completeness. Coverage does not replace integration tests against MongoDB, Elasticsearch, or Redis, failure-injection tests, browser checks, Compose smoke, or Postman review flows. The current HTTP contract is in [the foundation contract](specs/001-platform-foundation/contracts/http-foundation.md), and its manual check is in [the quickstart validation](specs/001-platform-foundation/quickstart.md).

## Reviewer quick start

The finished repository must support a workflow no more complicated than:

```bash
cp .env.example .env
docker compose up --build -d
make smoke
```

The API is available at `http://localhost:8000`, OpenAPI at `/docs`, readiness at
`/health/ready`, metrics at `/metrics`, and the static UI shell at
`http://localhost:3000`. Compose waits for Mongo replica-set initialization and
healthy Elasticsearch and Redis services before starting the API. `make smoke`
uses a bounded deadline to post an event and verify canonical query, search, and
realtime statistics.

If smoke fails, the stack remains available for inspection with `docker compose
ps`; reset it with `docker compose down -v`.

Reset all local data with:

```bash
docker compose down -v
```

The API and UI containers run as non-root users. Redis is unauthenticated in the
local defaults; set `REDIS_PASSWORD` and update `EVENT_PLATFORM_REDIS_URL` in
`.env` together when a password is required.

Later reviewer features will extend this quick start with:

- Demo UI URL
- FastAPI/OpenAPI URL
- health URLs
- Prometheus metrics URL
- Postman import/run instructions
- unit/integration/failure test commands

The final submission documentation will also include:

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

## Integration lifecycles

Feature 019's lifecycle scenarios use real MongoDB, Elasticsearch, and Redis endpoints supplied through `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL`. The feature covers HTTP ingestion to canonical query, Mongo change-stream projection to search, analytics grouping, realtime cache miss/hit, duplicate redelivery, and online rebuild continuity. Run `make test-integration`; missing or unavailable services are explicit skips, not passing evidence. Feature 019 scenarios use unique namespaces, bounded poll-until assertions, and cleanup in `finally` blocks.

Feature 020's deterministic failure selection runs without external endpoints:
`make test-failure` currently passes 29 tests. See the [failure-suite
README](tests/failure/README.md) for the covered invariants and keep this
evidence separate from Feature 019's service-backed integration lifecycles.
