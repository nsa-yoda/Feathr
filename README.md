# Feathr — Distributed Event Processing Platform

[![CI](https://github.com/nsa-yoda/Feathr/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/nsa-yoda/Feathr/actions/workflows/ci.yml)
[![Release validation](https://github.com/nsa-yoda/Feathr/actions/workflows/release.yml/badge.svg)](https://github.com/nsa-yoda/Feathr/actions/workflows/release.yml)

<p align="center">
  <img src="logo.png" alt="Feathr Distributed Event Processing Platform" width="640">
</p>

Feathr is a production-oriented distributed event processing platform for ingesting, processing, querying, searching, aggregating, and caching web events. FastAPI accepts validated events asynchronously into an SQS-style queue. MongoDB is the canonical event store, Elasticsearch is an eventually consistent and rebuildable search projection, and Redis provides realtime cache and distributed rate-limit state.

The design makes acknowledgement boundaries, idempotency, retries, DLQ handling, derived-service degradation, online Elasticsearch rebuilds, and operational visibility explicit. These guarantees are exercised through layered unit, functional, service-backed integration, acceptance, E2E, smoke, and failure tests. The local queue remains process-local by design, so its crash-durability limitation is documented rather than hidden.

## Key properties

- Asynchronous `POST /events` acceptance with an explicit `202 Accepted` boundary.
- MongoDB as the authoritative source of truth.
- Elasticsearch as a rebuildable, eventually consistent search projection.
- Redis as disposable realtime cache and distributed rate-limit state.
- At-least-once processing with duplicate-safe persistence and idempotency.
- Bounded retry/backoff behavior and a simulated DLQ after exhaustion.
- Graceful queue admission stop and worker draining during shutdown.
- Online Elasticsearch rebuilds with live-write convergence, identity verification, and one atomic alias swap.
- Leaky-bucket rate limiting with bounded delayed admission and a conservative local fallback when Redis is unavailable.
- Health, structured logs, request IDs, metrics, queue gauges, projection lag, and dependency visibility.
- Docker Compose startup with Mongo replica-set initialization and storage bootstrap.
- Layered automated quality gates and release validation.

## Architecture at a glance

```text
                    ┌─────────────────┐
                    │   POST /events  │
                    └────────┬────────┘
                             │ 202 Accepted
                             ▼
                    ┌─────────────────┐
                    │ SQS-style Queue │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Background      │
                    │ Worker          │
                    └────────┬────────┘
                             │ durable insert
                             ▼
                    ┌─────────────────┐
                    │ MongoDB         │
                    │ Canonical State │
                    └───────┬─────────┘
                            │ change stream
               ┌────────────┴─────────────┐
               ▼                          ▼
       ┌───────────────┐          ┌───────────────┐
       │ Elasticsearch │          │ Redis         │
       │ Search        │          │ Cache / Limit │
       └───────────────┘          └───────────────┘
```

MongoDB is authoritative. Elasticsearch is derived, eventually consistent, and can be rebuilt without changing canonical events. Redis is disposable derived state; its loss does not lose events. Queue admission is process-local and is therefore not durable across catastrophic process loss. The production path is an SQS-compatible external queue, described in [`docs/operations/sqs-migration.md`](docs/operations/sqs-migration.md).

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full failure model, indexing rationale, scaling path, rebuild protocol, and production evolution plan.

## Quick start

The complete reviewer path is:

```bash
cp .env.example .env
docker compose up --build -d
make smoke
```

Compose initializes the MongoDB replica set, runs the versioned storage-index bootstrap, waits for MongoDB, Elasticsearch, and Redis health, and then starts the API and UI. `make smoke` verifies the live lifecycle:

```text
ingest → async worker → Mongo query → Elasticsearch search
       → Mongo analytics → Redis realtime statistics
```

Useful local URLs:

| Surface | URL |
|---|---|
| API | <http://localhost:8000> |
| OpenAPI | <http://localhost:8000/docs> |
| Reviewer UI | <http://localhost:3000> |
| Liveness | <http://localhost:8000/health/live> |
| Readiness | <http://localhost:8000/health/ready> |
| Metrics | <http://localhost:8000/metrics> |

To remove containers and all local service data:

```bash
docker compose down -v --remove-orphans
```

The equivalent repeatable Make targets are `make compose-config`,
`make compose-up`, `make compose-down`, and `make compose-reset`. `make smoke`,
`make postman`, `make rebuild-status`, and `make rebuild-demo` cover the main
reviewer and operator workflows.

## API

All public API errors use the repository's `application/problem+json` contract. The exhaustive schemas and interactive examples are available at `/docs`.

| Method | Path | Purpose | Backing system / consistency |
|---|---|---|---|
| `POST` | `/events` | Validate and enqueue an event | Process-local queue; asynchronous `202` |
| `GET` | `/events` | Filtered, cursor-paginated canonical events | MongoDB; authoritative |
| `GET` | `/events/stats` | Bounded time-bucket aggregation | MongoDB; authoritative |
| `GET` | `/events/stats/realtime` | Rolling event-type statistics | MongoDB with Redis cache-aside |
| `GET` | `/events/search` | Full-text and exact-filter search | Elasticsearch; eventually consistent |
| `GET` | `/events/search/rebuild` | Latest or selected rebuild state | MongoDB; operational state |
| `GET` | `/health/live` | Process liveness | Dependency-free |
| `GET` | `/health/ready` | Readiness snapshot | MongoDB, Elasticsearch, Redis, queue, workers |
| `GET` | `/health/components` | Component health without readiness status | Health registry |
| `GET` | `/metrics` | Lightweight metrics exposition | In-process registry |
| `GET` | `/operations/visualizer` | Consolidated UI snapshot | Health, metrics, MongoDB/Redis realtime data |

`/metrics` exposes Prometheus-compatible text exposition backed by the platform's lightweight in-process metrics registry. No Prometheus server, OpenTelemetry collector, or Grafana deployment is required for the assignment stack. The registry includes bounded counters, latency histograms, queue and worker gauges, projection lag, and dependency metrics.

### Ingest an event

```bash
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{
    "event_type": "pageview",
    "timestamp": "2026-09-21T12:00:00Z",
    "user_id": "user-123",
    "source_url": "https://example.com/docs",
    "metadata": {
      "browser": "Firefox",
      "device": "desktop"
    }
  }'
```

Successful admission returns `202 Accepted` with an event ID, `status: queued`, and a request ID. It confirms validation and local queue admission; it does not claim Mongo persistence or Elasticsearch visibility, and it cannot make a volatile in-process queue survive a process crash.

### Query, aggregate, and search

```bash
# Canonical MongoDB query
curl 'http://localhost:8000/events?event_type=pageview&user_id=user-123&limit=50'

# Hourly MongoDB analytics
curl 'http://localhost:8000/events/stats?bucket=hour'

# Elasticsearch projection search
curl 'http://localhost:8000/events/search?q=docs&event_type=pageview&limit=20'

# Realtime MongoDB statistics with Redis cache-aside
curl 'http://localhost:8000/events/stats/realtime?window_minutes=5'
```

## Processing and consistency model

`POST /events` validates the typed event and reserves any supplied `Idempotency-Key` before admitting the immutable event envelope to the bounded queue. The persistence worker receives messages at least once, renews visibility while work is active, persists to MongoDB, and acknowledges only after durable insert or verified duplicate equivalence. Transient failures use bounded retry/backoff; exhausted or permanent failures are routed to the simulated DLQ.

Graceful shutdown stops new queue admission, allows the persistence worker to drain within the configured deadline, and records residual volatile work if the deadline expires. A process crash can still lose messages that existed only in the local queue. Replacing this adapter with SQS changes the durability and scaling boundary without changing the worker's at-least-once/idempotent logic.

MongoDB remains canonical for queries and analytics. The change-stream projector writes Elasticsearch outside the ingestion acknowledgement path, so Elasticsearch outages degrade search and projection health without losing canonical ingestion. Redis failures bypass the cache and use bounded local rate-limit protection; Redis never becomes the source of event truth.

Online Elasticsearch rebuilds create a candidate generation, enable candidate live writes before the bounded historical scan, capture an independent Mongo change-stream source fence, backfill through the `_id` bound, wait for the projector to reach the source fence, verify event identity/content, and perform one atomic stable-alias swap. `_id` is only a historical scan bound; Mongo change-stream cluster time is the convergence watermark and resume tokens remain opaque restart cursors. See the [Elasticsearch rebuild runbook](docs/operations/elasticsearch-rebuild.md).

## Configuration

Copy `.env.example` for the complete local Compose configuration. The table below groups the settings that matter most at runtime; defaults and validation limits live in `.env.example` and `src/event_platform/core/settings.py`.

| Area | Environment variables |
|---|---|
| Runtime and limits | `EVENT_PLATFORM_ENV`, `EVENT_PLATFORM_LOG_LEVEL`, `EVENT_PLATFORM_DEPENDENCY_TIMEOUT_SECONDS`, `EVENT_PLATFORM_REQUEST_BODY_MAX_BYTES`, `EVENT_PLATFORM_REQUEST_QUERY_MAX_BYTES` |
| MongoDB | `EVENT_PLATFORM_MONGO_URL`, `EVENT_PLATFORM_MONGO_DATABASE`, `EVENT_PLATFORM_MONGO_COLLECTION` |
| Elasticsearch | `EVENT_PLATFORM_ELASTICSEARCH_URL`, `EVENT_PLATFORM_ELASTICSEARCH_ALIAS` |
| Redis | `EVENT_PLATFORM_REDIS_URL`, `REDIS_PASSWORD` |
| Queue and workers | `EVENT_PLATFORM_QUEUE_CAPACITY`, `EVENT_PLATFORM_QUEUE_VISIBILITY_TIMEOUT`, `EVENT_PLATFORM_QUEUE_SEND_TIMEOUT`, `EVENT_PLATFORM_WORKER_CONCURRENCY`, `EVENT_PLATFORM_SHUTDOWN_GRACE_PERIOD` |
| Idempotency and cache | `EVENT_PLATFORM_IDEMPOTENCY_REPLAY_WINDOW_SECONDS`, `EVENT_PLATFORM_REALTIME_CACHE_TTL_SECONDS`, `EVENT_PLATFORM_REALTIME_DEFAULT_WINDOW_MINUTES`, `EVENT_PLATFORM_REALTIME_MAX_EVENT_TYPES` |
| Cursor and production auth | `EVENT_PLATFORM_CURSOR_SIGNING_KEY`, `EVENT_PLATFORM_CURSOR_PREVIOUS_SIGNING_KEY`, `EVENT_PLATFORM_PRODUCTION_API_TOKEN` |
| Rate limiting | `EVENT_PLATFORM_RATE_LIMIT_MAX_DELAYED_REQUESTS`, plus the ingestion, normal, expensive, and operations capacity/refill/cost settings |
| Compose | `COMPOSE_PROJECT_NAME`, `APP_PORT`, `UI_PORT`, `MONGO_PORT`, `ELASTICSEARCH_PORT`, `REDIS_PORT`, `MONGO_INIT_DEADLINE_SECONDS`, `ES_JAVA_OPTS` |

Production secrets, cursor keys, and bearer tokens belong in a deployment secret manager. The local Compose profile intentionally publishes MongoDB, Elasticsearch, and Redis host ports for integration testing; keep those ports private or remove the bindings in a deployment.

## Mongo storage bootstrap

Storage bootstrap is additive and idempotent. The Compose `storage-bootstrap` service runs it before the API starts. For a manually configured MongoDB:

```bash
uv run --locked python -m event_platform.cli storage bootstrap
uv run --locked python -m event_platform.cli storage verify
```

`storage bootstrap` creates the versioned event, checkpoint, rebuild, projector lease, idempotency, and schema-state indexes. `storage verify` is read-only and is also the invariant checked by application startup.

## Security boundary

Local development permits the documented Compose defaults. In production, configure `EVENT_PLATFORM_ENV=production`, a canonical MongoDB URL, a shared cursor signing key, and `EVENT_PLATFORM_PRODUCTION_API_TOKEN`. Protected routes require a bearer token; `/health/live` remains dependency-free for container liveness. TLS termination, tenant identity, and role authorization belong at a trusted deployment edge because this repository defines a shared operator-token boundary rather than a full tenant identity system.

## Reviewer UI and live Visualizer

The assignment is backend-focused; the UI is an optional reviewer and demo aid, not a replacement for the backend architecture. It is a static same-origin console served by unprivileged nginx and proxies `/api/` to the FastAPI app.

Shareable paths are `/dashboard`, `/generator`, `/events`, `/search`, `/analytics`, `/realtime`, `/visualizer`, and `/operations`; `/` opens the dashboard. The Visualizer uses the locally vendored D3 7.9.0 dependency and polls `/api/operations/visualizer` approximately every 500 ms without overlapping requests. It pauses while the tab is hidden, retains a bounded five-minute/600-sample history, preserves text selections and scroll position, and charts throughput, event types, queue health, latency, cache effectiveness, projection processing delay, and dependency health.

Frontend checks:

```bash
cd frontend
npm ci
npm run vendor
npm test
```

## Testing and quality gates

Tests are layered by failure radius. Pure business and state-machine semantics are isolated at unit level; HTTP contracts are covered functionally; MongoDB, Elasticsearch, Redis, and change streams are exercised against real services; critical distributed-system guarantees are executable acceptance contracts; and the full Compose stack is checked through smoke and black-box E2E tests.

| Layer | Command | Purpose |
|---|---|---|
| Formatting | `make format-check` | Ruff formatting gate |
| Lint | `make lint` | Ruff error, import, and simplification checks |
| Types | `make typecheck` | Strict MyPy over backend source |
| Dependency consistency | `make dependency-check` | Locked resolution and package checks |
| Unit | `make test-unit` | Isolated domain, queue, storage, lifecycle, and service semantics |
| Functional | `make test-functional` | HTTP validation, middleware, routing, and public error contracts |
| Failure | `make test-failure` | Deterministic outage, retry, ownership, cancellation, and recovery cases |
| Optional integration | `make test-integration` | Integration collection with explicit dependency-optional skips |
| Required integration | `make test-integration-required` | Real MongoDB replica set, Elasticsearch, Redis, change streams, and bootstrap |
| Acceptance | `make test-acceptance-required` | Online rebuild, live writes, fencing, verification, and atomic alias cutover |
| E2E | `E2E_BASE_URL=http://localhost:8000 make test-e2e-required` | Black-box ingestion/query/search/statistics flows |
| Coverage | `make coverage` | Branch-aware backend coverage with a 90% enforced floor |
| Smoke | `make smoke` | Clean-stack readiness and ingest-to-query lifecycle |
| Performance | `PERF_BASE_URL=http://localhost:8000 make performance` | Lightweight p50/p95/p99 regression probe |
| Postman | `make postman` | Reviewer collection against the running API; requires Newman |

`make all` runs the fast local quality set. Latest recorded counts and command results are maintained in [`QUALITY-GATES-REPORT.md`](QUALITY-GATES-REPORT.md); the exact clean-stack and rebuild validation record is in [`FINAL_VALIDATION_RECORD.md`](FINAL_VALIDATION_RECORD.md). Coverage is a guardrail, not a substitute for service-backed behavior, failure injection, or acceptance evidence.

The testing priority is to prove failure boundaries and recovery behavior before adding breadth. Further work would focus on long-running multi-replica load profiles, deployment-edge tenant authorization, and sustained projector/load behavior under representative production traffic.

## CI and release validation

Pull requests and pushes to `main` run [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Its quality job performs locked installation, formatting, Ruff, MyPy, dependency checks, Compose validation, source-archive hygiene, unit/functional/failure tests, branch-aware coverage, and diff checks. Its service job resets Compose and runs smoke, required integration, rebuild acceptance, E2E, and performance checks. A dependent Docker job validates the Compose configuration and builds the application and UI images. Required service jobs fail when required dependencies or cases are unavailable; they do not turn skips into green evidence.

Tags matching `v*.*.*` run [`.github/workflows/release.yml`](.github/workflows/release.yml) as a deployment simulation. Release validation repeats the quality, coverage, Compose, smoke, integration, acceptance, E2E, performance, and Docker gates, then produces a source archive, build metadata, SHA-256 checksums, coverage XML, performance output, and Compose logs. The current workflow does not claim to produce an SBOM.

## Postman reviewer suite

The [`postman/`](postman/) directory contains the collection and local Docker environment used for the reviewer flow. Import the collection and environment, start Compose, and run the numbered folders in order. The collection captures an event ID and uses bounded polling for canonical and Elasticsearch visibility. `make postman` exits with a diagnostic if Newman is not installed or the API is unavailable; it never hides a failed request.

## AI in My Workflow

The repository used ChatGPT/GPT-5.6 Sol, Codex, Serena MCP, and Spec Kit workflows. AI assisted with repository exploration, architecture decomposition, typed boundary design, adversarial review, test scaffolding, Docker/CI quality gates, and documentation consistency. Serena searches were used to trace actual ownership across the API, queue, worker, MongoDB, Elasticsearch, Redis, Compose, and frontend layers before editing.

The most valuable corrections came from challenging proposed guarantees. An early rebuild design treated MongoDB ObjectId ordering too strongly. Review identified that a writer can allocate an ObjectId before its insert commits, so ObjectId cannot be the convergence watermark. The implementation now uses `_id` only as `backfill_upper_bound`, enables candidate dual-write before the scan, captures an independent Mongo change-stream `source_fence`, compares ordered `clusterTime` values, keeps resume tokens opaque, verifies identities, and swaps the stable alias atomically only after projector convergence. Other review corrections preserved canonical ingestion when Elasticsearch fails, fenced producer/projector races, and removed unsupported test claims when runtime evidence was missing.

AI accelerated architecture searches, adversarial scenarios, regression tests, and cross-document checks. Acceptance remained evidence-driven: repository code, executable tests, service-backed runs, and observed runtime behavior overruled generated suggestions. The detailed chronology is in [`docs/ai-workflow-log.md`](docs/ai-workflow-log.md).

## Deliberate tradeoffs

- The in-process SQS-style queue is volatile if the whole process terminates; SQS or an equivalent durable queue is the production migration path.
- Elasticsearch is eventually consistent and may be degraded while MongoDB continues accepting canonical events.
- Redis is disposable cache and rate-limit coordination state, not event truth.
- The production security boundary uses a shared bearer token; tenant and role identity are expected at a trusted edge rather than invented in this service.
- The performance command is a repeatable regression probe, not a capacity or service-level claim.
- Local Compose publishes dependency ports to support developer and integration testing; a deployment should keep those ports private.

## Local development

The backend supports Python `>=3.12`, as declared in `pyproject.toml`. The
`uv.lock` lockfile is consumed by `uv sync --locked`; the application image
uses Python 3.14.7-slim, and CI validates the locked environment on Python 3.14
with uv 0.12.17.

```bash
cp .env.example .env
uv sync --locked
uv run --locked uvicorn event_platform.main:create_app --factory \
  --log-config src/event_platform/core/uvicorn_logging.json \
  --host 127.0.0.1 --port 8000 --workers 1
```

That direct process is useful for API and functional work. Use the Compose quick start when MongoDB, Elasticsearch, Redis, change streams, storage bootstrap, the worker, or the reviewer UI are part of the scenario.

## Repository guide

```text
src/event_platform/   Backend application, domain, queue, storage, and integrations
tests/                 Unit, functional, failure, integration, E2E, and acceptance tests
frontend/              Optional reviewer UI and D3 Visualizer
docs/                  Architecture, operations, testing, and workflow documentation
postman/               Reviewer API collection and local environment
scripts/               Smoke, integration, performance, and release helpers
.github/workflows/     CI and tagged-release validation
```

## Further documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system boundaries, failure modes, indexes, rebuild protocol, scaling, and deployment topology.
- [`QUALITY-GATES-REPORT.md`](QUALITY-GATES-REPORT.md) — latest test layers, coverage, performance, smoke, and release evidence.
- [`FINAL_VALIDATION_RECORD.md`](FINAL_VALIDATION_RECORD.md) — convergence invariant, service-backed acceptance, and clean-stack validation commands.
- [`docs/operations/elasticsearch-rebuild.md`](docs/operations/elasticsearch-rebuild.md) — online rebuild runbook and evidence.
- [`docs/operations/sqs-migration.md`](docs/operations/sqs-migration.md) — durable production queue migration design.
- [`tests/failure/README.md`](tests/failure/README.md) — deterministic failure and recovery coverage.
- [`postman/README.md`](postman/README.md) — reviewer collection setup.
- [`docs/ai-workflow-log.md`](docs/ai-workflow-log.md) — detailed AI collaboration and review chronology.
