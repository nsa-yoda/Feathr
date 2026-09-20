# AUTO_CODE_REVIEW_2 Remediation Report

**Date:** 2026-09-20
**Scope:** backend/runtime remediation of every finding in `AUTO_CODE_REVIEW_2.md`
**Status vocabulary:** `FIXED` means implemented and regression tested; `ALREADY RESOLVED` means the reviewed revision already satisfied the finding; `INTENTIONALLY DEFERRED` means the assignment does not define the production capability and the limitation is documented.

## Executive summary

The verified P0 and P1 correctness findings are fixed in the current revision. The runtime now separates queue admission shutdown from persistence-worker draining, enforces critical versus degradable task behavior, fences producer idempotency and Elasticsearch projector ownership with Mongo CAS/lease state, batches Elasticsearch writes, bounds delayed rate-limit waiters, and preserves compatibility with pre-ACR2 search documents. MongoDB remains canonical; Elasticsearch and Redis remain derived/degradable. The in-process queue is still intentionally volatile across a process crash, as required by the interview assignment.

The remaining intentional limits are the assignment's single static bearer-token security model, raw Mongo analytics instead of materialized rollups, and the deliberately small typed lifespan composition root. Each is called out below and in `ARCHITECTURE.md`/`docs/operations/runtime-guarantees.md`.

## Finding-by-finding disposition

### P0

| Finding | Status | Evidence and changed files |
|---|---|---|
| P0-01 graceful shutdown could lose accepted events | **FIXED** | `core/lifecycle.py` now stops admission first, drains drainable workers until queue empty or deadline, then cancels. Persistence uses `TaskPolicy(drain_on_shutdown=True)`. Regression tests cover accepted work during shutdown and residual deadline behavior. |
| P0-02 degradable Elasticsearch failure poisoned global lifecycle | **FIXED** | `core/lifecycle.py` now records degradable task failure without stopping canonical admission. `main.py` makes readiness depend on Mongo/queue/persistence, while projector health is reported independently. Lifecycle degradation tests added. |
| P0-03 authentication lacked production tenant/role authorization | **INTENTIONALLY DEFERRED** | The assignment specifies a static bearer token and no tenant/role contract. Production tokens now produce a stable hashed `client_scope` for idempotency/rate-limit isolation in `api/middleware/production_auth.py`; full identity provider, scopes, and resource authorization remain a documented production evolution. |

### P1

| Finding | Status | Evidence and changed files |
|---|---|---|
| P1-01 idempotency reservation was separate from queue admission | **FIXED** | `storage/idempotency.py` adds owner tokens, explicit reserved/enqueued states, and owner-fenced release. `api/routes/events.py` releases reservations on definitive `QueueFull`/`QueueClosed` admission failure. Retry-after-admission ambiguity remains documented because the queue is intentionally in-process. |
| P1-02 stale takeover lacked CAS | **FIXED** | Mongo stale takeover matches observed token/generation/timestamp/status and requires the atomic update winner; in-memory behavior mirrors generation fencing. Registry tests cover owner fencing and retry. |
| P1-03 idempotency scope collapsed clients into anonymous | **FIXED for assignment boundary** | Production auth derives a stable token scope; local direct/test mode uses an explicit single-client scope. Ingestion uses `request.state.client_scope`. Full tenant authorization is the deferred P0-03 capability. |
| P1-04 projector ownership/checkpoints could regress across replicas | **FIXED** | New `storage/projection_leases.py` implements Mongo lease acquire/renew/release with generation fencing. `main.py` renews and stops on ownership loss; checkpoint writes require owner/generation. Lease tests cover takeover and stale renew fencing. |
| P1-05 serial Elasticsearch projection | **FIXED** | `search/projection.py` batches up to 100 events and checkpoints only acknowledged events; `search/elasticsearch.py` uses bounded bulk writes and classifies partial/error responses for retry. Bulk and partial-failure tests added. |
| P1-06 expensive routes misclassified | **FIXED** | `rate_limit/service.py` classifies `/events/search`, stats/analytics, search, and rebuild operations explicitly; route classification tests cover the real paths. |
| P1-07 delayed rate limiting had no global cap | **FIXED** | `RateLimitMiddleware` uses a process-wide bounded semaphore and `rate_limit_max_delayed_requests`; excess delayed work receives the final bounded 429 only after the configured backlog is exhausted. |
| P1-08 raw Mongo analytics scale linearly | **INTENTIONALLY DEFERRED** | Existing bounded date range, canonical indexes, and aggregation behavior remain appropriate for the assignment. `ARCHITECTURE.md` documents materialized counters/rollups as the next evolution when measured volume warrants them. |

### P2

| Finding | Status | Evidence and changed files |
|---|---|---|
| P2-01 idempotency storage was outside the manifest | **FIXED** | `storage/bootstrap.py` now governs `event_idempotency` with a 30-day TTL and `search_projection_leases`; manifest fingerprint and verification tests cover the expanded schema. |
| P2-02 CI could pass with integration skips | **FIXED** | `.github/workflows/ci.yml` starts Compose for the required integration job, removes optional skip semantics, and tears the stack down. |
| P2-03 rebuild CLI was a stub | **FIXED** | `search/rebuild.py` status reads durable Mongo rebuild state and emits bounded JSON; execution remains guarded by the existing application harness and explicit confirmation. Operational docs were updated. |
| P2-04 README AI disclosure incomplete | **FIXED** | `README.md` now names ChatGPT running GPT-5.6 Sol and Codex, and retains concrete accepted/challenged AI workflow history. |
| P2-05 README lacked testing philosophy/future priorities | **FIXED** | `README.md` now explains the failure-oriented testing approach and what would be prioritized with more time. |
| P2-06 architecture overstated shutdown drain | **FIXED** | `ARCHITECTURE.md` and `docs/operations/runtime-guarantees.md` describe admission stop, bounded drain, residual deadline behavior, and unavoidable process-loss limits accurately. |
| P2-07 CORS omitted Authorization | **FIXED** | `security_headers.py` allows `Authorization` and caches the configured middleware instead of rebuilding it per request; security tests cover the header. |
| P2-08 search projection stored internal hashes | **FIXED** | New projection documents omit payload/idempotency hashes and mappings no longer index them. Search strips those fields from old generations and reconstructs the canonical payload hash at the typed boundary for online compatibility. |
| P2-09 local bucket eviction was O(n) per request | **FIXED** | `rate_limit/local_bucket.py` evicts expired entries from the ordered front incrementally. |
| P2-10 metrics lacked latency/lag gauges | **FIXED** | `observability/metrics.py` now provides fixed-bucket latency histograms and current-state gauges. API middleware, queue, worker, Mongo, Elasticsearch, Redis, projection, and cache boundaries record bounded measurements; `/metrics` and the operations UI expose them. Focused histogram, gauge, queue, worker, and frontend transformation tests were added. |
| P2-11 lifespan composition root was high fanout | **INTENTIONALLY DEFERRED** | `core/composition.py` provides a typed application-service boundary and the lifespan remains the explicit ownership/composition root. Splitting further would add indirection without changing the assignment's service boundaries; this tradeoff is documented. |

### P3

| Finding | Status | Evidence and changed files |
|---|---|---|
| P3-01 duplicate active queue message IDs | **FIXED** | `InProcessQueue.send()` rejects an active explicit ID; queue regression test added. |
| P3-02 stale rebuild metrics route | **ALREADY RESOLVED** | The reviewed revision already maps `/operations/search-rebuild` to the bounded `rebuild` family; no unnecessary change was made. |
| P3-03 per-request CORS middleware construction | **FIXED** | `ConfiguredCORSMiddleware` reuses the configured Starlette middleware and only rebuilds when the origin configuration changes. |
| P3-04 coverage was not enforced | **FIXED** | Makefile and CI enforce `coverage report --fail-under=90`; current backend branch coverage is 90%. |
| P3-05 placeholder package duplication | **FIXED** | Removed the unused `application/` and plural `workers/` marker packages. Updated the foundation plan/tasks, target layout, handoff inventory, and checksum manifest to describe the concrete `core`, singular `worker`, and `search` ownership boundaries. Runtime imports and packaging remain unchanged. |

## Tests added or modified

- Lifecycle drain and degradable-task isolation tests in `tests/unit/test_lifecycle.py`.
- Queue duplicate-ID regression in `tests/unit/test_in_process_queue.py`.
- Owner-fenced idempotency release/retry tests in `tests/unit/test_idempotency_registry.py`.
- Projector lease acquisition/takeover/fencing tests in `tests/unit/test_projection_leases.py`.
- Bulk projection and partial-failure coverage in `tests/unit/test_search_projection.py`.
- Legacy search-document compatibility coverage in `tests/unit/test_search.py`.
- Mongo rebuild optional-lock collection regression in `tests/unit/test_search_rebuild.py`.
- Storage manifest/index expectations updated in `tests/unit/test_storage_bootstrap.py`.
- CORS and rate-limit route tests updated in the existing security/rate-limit suites.

## Architectural implications

- API admission now has an explicit acknowledgement boundary: `202` means the event entered the bounded in-process queue; the persistence worker acknowledges/deletes only after canonical Mongo insertion or a deliberate DLQ disposition.
- Graceful shutdown stops new admission, drains accepted messages within a deadline, and reports residual work. A process crash can still lose volatile queue contents; production migration is documented as SQS/Kafka-equivalent durable publication.
- MongoDB remains the source of truth. Elasticsearch is an asynchronously leased, fenced, bulk-written projection; Redis remains a degradable cache/rate-limit dependency.
- Idempotency is owner-fenced and client-scoped at the assignment boundary. A durable outbox remains the production answer for atomically coupling publication to canonical persistence across process failure.
- Existing Elasticsearch generations remain readable during online migration because the search boundary removes legacy derived fields and reconstructs the required canonical integrity field.

## Remaining known limitations

1. The queue is intentionally process-local and volatile, so a hard process crash cannot recover an accepted-but-not-yet-persisted message.
2. Static bearer authentication is not a complete multi-tenant IAM/authorization system.
3. A failure after queue admission but before idempotency completion is handled conservatively and may require replay/reconciliation; the durable outbox path is documented for production.
4. Raw Mongo analytics and the intentionally dependency-free in-process metrics registry are assignment-sized implementations; materialized rollups and an operated export backend are the next scale steps.
5. The integration suite is available but direct venv execution skips its 12 service-marked tests; Compose smoke exercised live Mongo, Elasticsearch, Redis, API, UI, ingestion, canonical query, search, and realtime stats paths.

## Validation commands and results

| Command | Result |
|---|---|
| `git diff --check` | Passed |
| `./.venv/bin/ruff check src tests` | Passed |
| `./.venv/bin/mypy src` | Passed |
| `./.venv/bin/pytest -q tests/unit tests/failure` | **418 passed**, 2 dependency deprecation warnings |
| `./.venv/bin/pytest -q tests/integration -m integration` | 12 skipped because service-backed integration mode was not enabled in the direct venv run |
| `./.venv/bin/coverage run --branch --source=src/event_platform -m pytest -q tests/unit` + `coverage report --fail-under=90` | **389 passed; 90% total branch coverage; gate passed** |
| `docker compose --env-file .env.example config --quiet` | Passed |
| `docker compose --env-file .env.example up --build -d` | Passed; storage bootstrap verified 13 indexes; app and UI healthy |
| `make smoke` | Passed; live event `aec3d8aa-c3e0-4d3a-b919-b859ee19934f` reached canonical query, search, and realtime stats |
| `make postman` | Not runnable: Newman is not installed on PATH; target failed with its explicit prerequisite message |

All findings, status check-ins, validation results, and corrective discoveries were appended to `CODEX_WORK.LOG` with timestamps. The completed Spec Kit task list is in `specs/038-ACR2_runtime-correctness-hardening/tasks.md`.
