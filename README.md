# Distributed Event Processing Platform

> **Current state:** Features 001-025 provide the API, data services, lifecycle controls, failure coverage, Docker Compose configuration, and executable Postman reviewer suite plus the reviewer operations UI. Static gates pass, and the clean Compose smoke plus the Newman collection pass on the local Colima Docker context; browser, online rebuild, and hosted CI evidence remain environment-specific gates. See `CODEX-HANDOFF.md` and the active Spec Kit artifacts.

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

`make rebuild-demo` prints the guarded rebuild command and its dependency-harness
requirement; use `make rebuild-status` for a read-only check. The direct CLI
forms are `uv run --locked python -m event_platform.cli search rebuild-status`
and `uv run --locked python -m event_platform.cli search rebuild --confirm`.

CI uses Python 3.12, a pinned uv release, and `uv.lock` with `--locked`
resolution.

The unit suite is the isolated semantic suite for settings, lifecycle, queue/worker state, query/search/analytics contracts, caching, rate limiting, request IDs, and problem responses. `make coverage` measures executed source lines and branches and writes `coverage/coverage.xml`; it is a signal, not proof of semantic completeness. Coverage does not replace integration tests against MongoDB, Elasticsearch, or Redis, failure-injection tests, browser checks, Compose smoke, or Postman review flows. The current HTTP contract is in [the foundation contract](specs/001-platform-foundation/contracts/http-foundation.md), and its manual check is in [the quickstart validation](specs/001-platform-foundation/quickstart.md).

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

### Mongo storage bootstrap

Mongo schema ownership is explicit. Run the additive, idempotent bootstrap actor
before starting an application that is configured with Mongo:

```bash
uv run --locked python -m event_platform.cli storage bootstrap
uv run --locked python -m event_platform.cli storage verify
```

`storage bootstrap` creates the versioned event, projection-checkpoint, rebuild,
lease, and schema-state indexes. `storage verify` is read-only. Application
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
| Metrics | `/metrics` | Prometheus text, safe operational counters |
| Canonical events | `POST/GET /events` | Mongo-backed event acceptance/query |
| Search | `GET /events/search` | Eventually consistent Elasticsearch projection |
| Analytics/realtime | `/events/stats`, `/events/stats/realtime` | Mongo aggregation and Redis cache-aside |
| Rebuild status | `/events/search/rebuild` | Read-only Mongo-backed rebuild state |
| Reviewer UI | `http://localhost:3000` | Static console through nginx `/api/` proxy |

## Consistency and known limitations

MongoDB is canonical event state. Elasticsearch is an eventually consistent,
rebuildable projection and Redis is disposable cache/rate-limit state. A `202`
response confirms validated admission to the process-local queue; it is not
durable across application-process failure. Queue delivery is at-least-once,
and duplicate persistence is handled through immutable event IDs and hashes.
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

## AI in My Workflow

This repository records AI collaboration in [`docs/ai-workflow-log.md`](docs/ai-workflow-log.md). Codex used the Spec Kit workflows to turn each ordered request into accepted specifications, plans, contracts, checklists, tasks, implementation changes, convergence notes, and review evidence. Serena MCP searches were used to trace existing route, lifecycle, storage, queue, projection, cache, Compose, and documentation ownership before proposing changes.

Concrete examples include mapping Mongo as canonical and Elasticsearch/Redis as derived state; adding bounded Compose startup and smoke checks; building the Postman suite around actual response/problem contracts; creating the reviewer UI against the existing nginx `/api/` boundary; and adding locked Make/CI commands with coverage artifacts. Review agents then challenged incorrect assumptions: the Postman suite stopped claiming repeated requests reuse the original event ID, polling gained request timeouts and reachable degraded paths, the UI added filters/cursors and preserved degraded dashboard state, and the rebuild demo became a truthful guarded command instead of a failing promise.

Human judgment remained authoritative. The constitution, ADRs, accepted specifications, service contracts, and observed test/runtime evidence determined what was accepted. AI suggestions were rejected or narrowed when they would imply durable `202` acceptance, exactly-once processing, authoritative Elasticsearch/Redis state, unverified live services, or product-level UI scope.

## Reviewer operations UI

Open `http://localhost:3000` after the Compose stack is running. The console
provides dashboard, event generation, canonical events, eventually consistent
search, analytics, realtime cache status, and read-only operations views. Event
bursts are capped at 500 requests, with request starts paced across five seconds,
and all API errors render their safe problem fields.

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
`make test-unit`, `make test-integration`, and `make test-failure`. Unit and
failure selections run without external services; integration tests collect
real-service lifecycles and explicitly skip when MongoDB, Elasticsearch, or
Redis endpoints are unavailable. The recorded local Colima run passed clean
Compose smoke and all 45 Newman/Postman assertions; browser UI, online rebuild,
and hosted CI remain live gates that require their respective environments.

## Integration lifecycles

Feature 019's lifecycle scenarios use real MongoDB, Elasticsearch, and Redis endpoints supplied through `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL`. The feature covers HTTP ingestion to canonical query, Mongo change-stream projection to search, analytics grouping, realtime cache miss/hit, duplicate redelivery, and online rebuild continuity. Run `make test-integration`; missing or unavailable services are explicit skips, not passing evidence. Feature 019 scenarios use unique namespaces, bounded poll-until assertions, and cleanup in `finally` blocks.

Feature 020's deterministic failure selection runs without external endpoints:
`make test-failure` currently passes 29 tests. See the [failure-suite
README](tests/failure/README.md) for the covered invariants and keep this
evidence separate from Feature 019's service-backed integration lifecycles.
