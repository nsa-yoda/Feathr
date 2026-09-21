# Distributed Event Processing Platform

> **Current state:** Features 001-038 provide the API, data services, lifecycle controls, failure coverage, Docker Compose configuration, and executable Postman reviewer suite plus the reviewer operations UI. The ACR2 remediation keeps Mongo canonical, makes derived-service failure degradable, and adds fenced idempotency/projector ownership. Static gates pass locally; clean Compose smoke, browser, online rebuild, and hosted CI evidence remain environment-specific gates. See `CODEX-HANDOFF.md`, `AUTO_CODE_REVIEW_2.md`, and the active Spec Kit artifacts.

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
| `EVENT_PLATFORM_MONGO_URL` | unset for foundation-only local mode | MongoDB URI | Canonical storage; required in production and verified before workers start. |
| `EVENT_PLATFORM_MONGO_DATABASE` | `event_platform` | Mongo database name | Canonical and operational storage database. |
| `EVENT_PLATFORM_MONGO_COLLECTION` | `events` | Mongo collection name | Canonical event collection covered by the storage manifest. |

An invalid foundation setting aborts startup before serving. The diagnostic names the field without printing its supplied value. Later feature settings will be documented as those integrations land.

`EVENT_PLATFORM_RATE_LIMIT_MAX_DELAYED_REQUESTS` bounds the process-wide queue of
requests waiting for a leaky-bucket slot. A request receives `429` only when that
bounded admission gate (or the distributed bucket backlog) is full. Keep this value
bounded per replica; Redis remains the cross-replica limiter.

Run the foundation checks with:

```bash
make format-check
make lint
make typecheck
make dependency-check
make test-unit
make test-functional
make test-integration
make test-integration-required   # requires MongoDB, Elasticsearch, and Redis
make test-acceptance-required    # service-backed online rebuild
make test-e2e-required           # requires E2E_BASE_URL
make test-failure
make coverage
make performance                # requires a running stack
```

Developer workflow targets:

```bash
make all
make compose-config
make compose-up
make smoke
make postman
make compose-down
# destructive local reset, when intended:
make compose-reset
make rebuild-status
make rebuild-demo
```

`make rebuild-demo` prints the guarded, executable online rebuild command. It
requires the Compose MongoDB replica set and Elasticsearch services; use
`make rebuild-status` for a read-only check. The direct CLI forms are
`uv run --locked python -m event_platform.cli search rebuild-status` and
`uv run --locked python -m event_platform.cli search rebuild --confirm`.

CI and the application image use Python 3.14.7 and uv 0.12.17. The Compose
baseline pins MongoDB 8.3.11, Elasticsearch 9.5.4, Redis 8.10.1, and the
unprivileged Nginx frontend at 1.31.6; `uv.lock` is always consumed with
`--locked` resolution.

The unit suite is the isolated semantic suite for settings, lifecycle state machines,
queue/worker acknowledgement boundaries, idempotency/projector races, query/search/
analytics contracts, caching, rate limiting, request IDs, and problem responses.
`make coverage` measures backend source lines and branches across unit,
functional, and failure tests and writes `coverage/coverage.xml`; it is a
guardrail, not proof of semantic completeness. The current quality floor is
90% total branch-aware coverage, with risk-based tests prioritized over trivial
line execution.
Coverage does not replace integration tests against MongoDB, Elasticsearch, or Redis,
failure-injection tests, browser checks, Compose smoke, or Postman review flows. The
testing philosophy is to prove state transitions and failure dispositions at unit level,
then run the same contracts through real dependencies when the environment supplies
them. With more time, the next tests would exercise two live API replicas racing on
Mongo leases/idempotency and a long-running bulk projector under lease loss.
The current HTTP contract is in [the foundation contract](specs/001-platform-foundation/contracts/http-foundation.md), and its manual check is in [the quickstart validation](specs/001-platform-foundation/quickstart.md).

For a service-backed acceptance run, set `MONGO_URI`, `ELASTICSEARCH_URL`, and
`REDIS_URL` and run `make test-integration-required`; that gate fails on missing
endpoints or skipped cases. `make test-integration` remains the local
dependency-optional selection. `make check-source-archive` checks tracked source
files for cache/bytecode/platform debris and required project inputs.

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


## Configuration and endpoint map

Copy `.env.example` to `.env` before Compose. The local defaults use API port
8000, reviewer UI port 3000, a Mongo replica set at `rs0`, Elasticsearch on
its Compose network, Redis without a password, a 90-second Mongo init deadline,
and bounded dependency/request limits. Set `REDIS_PASSWORD` together with a
matching authenticated Redis URL when credentials are required.

Compose also publishes Mongo, Elasticsearch, and Redis on host ports 27017,
9200, and 6379 for local integration tests. Keep those bindings private or
remove them in a production deployment.

### Mongo storage bootstrap

Mongo schema ownership is explicit. Run the additive, idempotent bootstrap actor
before starting an application that is configured with Mongo:

```bash
uv run --locked python -m event_platform.cli storage bootstrap
uv run --locked python -m event_platform.cli storage verify
```

`storage bootstrap` creates the versioned event, projection-checkpoint, rebuild,
projector-lease, idempotency, and schema-state indexes. `storage verify` is read-only. Application
lifespan performs the same verification before creating persistence or search
projector tasks; it never mutates shared schema. Production startup rejects a
missing canonical Mongo URL. Compose runs the bootstrap service after replica
set initialization and waits for it to complete before starting the API.

### Production security boundary

Production requires a canonical Mongo URL, shared cursor signing key, and
deployment-supplied `EVENT_PLATFORM_PRODUCTION_API_TOKEN`. Every route except
`/health/live` requires a bearer token; production responses include HSTS. Keep
tokens and cursor keys in the deployment secret manager, and terminate TLS plus
tenant/role authorization at the trusted production edge.

| Surface | URL/path | Ownership/behavior |
|---|---|---|
| OpenAPI | `http://localhost:8000/docs` | FastAPI contract discovery |
| Liveness/readiness/components | `/health/live`, `/health/ready`, `/health/components` | Process and dependency state |
| Metrics | `/metrics` | Prometheus text, bounded counters, latency histograms, and operational gauges |
| Canonical events | `POST/GET /events` | Mongo-backed event acceptance/query |
| Search | `GET /events/search` | Eventually consistent Elasticsearch projection |
| Analytics/realtime | `/events/stats`, `/events/stats/realtime` | Mongo aggregation and Redis cache-aside |
| Rebuild status | `/events/search/rebuild` | Read-only Mongo-backed rebuild state |
| Visualizer snapshot | `/operations/visualizer` | Consolidated read-only metrics, health, and cached realtime analytics |
| Reviewer UI | `http://localhost:3000` | Static console through nginx `/api/` proxy |

## Consistency and known limitations

MongoDB is canonical event state. Elasticsearch is an eventually consistent,
rebuildable projection and Redis is disposable cache/rate-limit state. A `202`
response confirms validated admission to the process-local queue; normal graceful
shutdown drains accepted work before closing the worker, but a process crash can still
lose volatile queued messages, so that admission is not durable across application-process failure. Queue delivery is at-least-once, and duplicate
persistence is handled through immutable event IDs and owner-fenced idempotency records.
The local stack is intentionally single-process; production SQS is the scaling
path described in `ARCHITECTURE.md` and `docs/operations/sqs-migration.md`.

## Postman reviewer suite

Import the v2.1 collection and local environment from `postman/`, then run the
numbered folders in order. The collection captures an event ID and uses bounded
polling for canonical query and Elasticsearch search. Newman users can run
`make postman`; the wrapper exits clearly when Newman or the API is unavailable. In
the recorded local live run, the same collection passed through
`npx --yes newman` because Newman was not installed globally.

Feature 025 reconciles the final architecture, traceability, and AI workflow documentation. The current reviewer URLs are:

- API docs: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`
- Component health: `http://localhost:8000/health/components`
- Metrics: `http://localhost:8000/metrics`

The metrics endpoint is intentionally a small in-process, dependency-free
observability surface for the interview assignment. It reports bounded counters,
fixed latency buckets, and current queue/worker/projection gauges without adding
Prometheus, OpenTelemetry, or Grafana to the stack. A production deployment can
export these same measurements through a monitoring adapter.

## AI in My Workflow

This repository records AI collaboration in [`docs/ai-workflow-log.md`](docs/ai-workflow-log.md). ChatGPT running GPT-5.6 Sol and Codex used the Spec Kit workflows to turn each ordered request into accepted specifications, plans, contracts, checklists, tasks, implementation changes, convergence notes, and review evidence. Serena MCP searches were used to trace existing route, lifecycle, storage, queue, projection, cache, Compose, and documentation ownership before proposing changes.

Concrete examples include mapping Mongo as canonical and Elasticsearch/Redis as derived state; adding bounded Compose startup and smoke checks; building the Postman suite around actual response/problem contracts; creating the reviewer UI against the existing nginx `/api/` boundary; and adding locked Make/CI commands with coverage artifacts. Review agents then challenged incorrect assumptions: the Postman suite stopped claiming repeated requests reuse the original event ID, polling gained request timeouts and reachable degraded paths, the UI added filters/cursors and preserved degraded dashboard state, and the rebuild demo became a truthful guarded command instead of a failing promise.

Human judgment remained authoritative. The constitution, ADRs, accepted specifications, service contracts, and observed test/runtime evidence determined what was accepted. AI suggestions were rejected or narrowed when they would imply durable `202` acceptance, exactly-once processing, authoritative Elasticsearch/Redis state, unverified live services, or product-level UI scope.

## Reviewer operations UI

Open `http://localhost:3000` after the Compose stack is running. The console
provides dashboard, event generation, canonical events, eventually consistent
search, analytics, realtime cache status, and read-only operations views. Event
bursts are capped at 500 requests, with request starts paced across five seconds,
and all API errors render their safe problem fields. The adjacent **Visualizer**
page adds D3 7.9.0 operational charts for throughput, event types, queue health,
latency buckets, cache effectiveness, projection lag, and dependency health. It
polls the consolidated `/api/operations/visualizer` snapshot every 500 ms
without overlapping requests, pauses while the tab is hidden, and retains only
600 samples (five minutes). Existing Realtime and other views remain unchanged.

The final submission documentation includes:

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

## Testing and evidence

The local static gates are `make format-check`, `make lint`, `make typecheck`,
`make coverage`, `make test-unit`, `make test-functional`, and `make test-failure`.
Service-backed targets require real MongoDB, Elasticsearch, and Redis and fail
when an expected case is skipped. `make smoke` is a clean-stack black-box gate;
`make performance` is a lightweight non-regression probe, while heavier load
tests remain an explicit manual or scheduled activity. CI retains coverage,
JUnit, Compose logs, performance output, and release checksums as artifacts.

## Integration lifecycles

Feature 019's lifecycle scenarios use real MongoDB, Elasticsearch, and Redis endpoints supplied through `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL`. The feature covers HTTP ingestion to canonical query, Mongo change-stream projection to search, analytics grouping, realtime cache miss/hit, duplicate redelivery, and the online rebuild continuity scenario. Run `make test-integration` for collection and `MONGO_URI=... ELASTICSEARCH_URL=... .venv/bin/pytest -q tests/integration/test_rebuild_live.py` for the required service-backed rebuild evidence. Missing or unavailable services are explicit skips, not passing evidence. Feature 019 scenarios use unique namespaces, deterministic barriers, bounded poll-until assertions, and cleanup in `finally` blocks.

Feature 020's deterministic failure selection runs without external endpoints:
`make test-failure` currently passes 29 tests. See the [failure-suite
README](tests/failure/README.md) for the covered invariants and keep this
evidence separate from Feature 019's service-backed integration lifecycles.
