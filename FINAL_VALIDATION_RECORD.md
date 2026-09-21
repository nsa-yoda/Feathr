# Final Validation Record

Date: 2026-09-21

## Assignment completion refresh

The final refresh closed five evidence gaps without changing the required
in-process queue architecture:

1. Replaced stale quality-report counts with the current 481-test collection,
   467-test coverage selection, and 91% branch-aware backend coverage.
2. Removed obsolete integration-skip/failure wording after a fresh 13/13
   service-backed integration pass.
3. Added an exact Newman 6.2.2 package lock and made `make postman` install/run it
   locally; no global Newman dependency remains.
4. Rebuilt the full Compose stack from empty volumes and reran smoke, integration,
   acceptance, E2E, Postman, and performance gates.
5. Added a bounded 500-event profile with concurrency 50, throughput and percentile
   reporting, zero-error enforcement, and exact accepted-ID reconciliation through
   both MongoDB and Elasticsearch.

## Rebuild convergence invariant

Mongo `_id` is used only as `backfill_upper_bound` for the majority-consistent
historical scan. It is not a commit-order or convergence watermark. The rebuild
opens an independent change-stream cursor immediately after candidate dual-write
is enabled. After backfill, the cursor is drained and its latest Mongo
`clusterTime`, represented losslessly as `(seconds, increment)`, is persisted as
`source_fence`. The projector must persist a position at or after that fence before
verification and alias cutover. Resume tokens remain opaque restart cursors and
are never numerically compared.

For the preallocated ObjectId race, writer X can allocate `_id` before the
backfill bound and commit after the bounded scan. Because the candidate target is
already active, X is observed by the independent change stream and dual-written
to the candidate. The source fence includes X's commit position, and cutover waits
for the projector to reach it. The service-backed acceptance test asserts X's
`_id` is below the bound, the scan indexes only A-C, X/D/E/F arrive during the
rebuild, and A-G are present through the stable alias after cutover.

## Historical integration-harness fixes retained

The first complete integration run had been 4 passed / 9 failed. Its legitimate
harness/product drift was corrected by:

- replacing obsolete `AsyncDatabase.drop()` calls with `drop_database(name)`;
- replacing removed Elasticsearch cleanup arguments with explicit 404 handling
  and concrete wildcard resolution;
- deriving the bootstrap assertion from the current 13-index storage manifest;
- gating API startup on persistence-worker and projector cursor readiness;
- using a current realtime-window fixture;
- keeping Elasticsearch cursors within one signed query scope.

The current required suite passes all 13 tests with no skips.

## Exact current validation commands and results

| Command | Result |
|---|---|
| `make format-check` | PASS; 142 Python files formatted |
| `make lint` | PASS |
| `make typecheck` | PASS; 60 source files |
| `make dependency-check` | PASS; lock current and installed packages compatible |
| `make check-source-archive` | PASS |
| `make compose-config` | PASS |
| `make test-unit` | PASS; 435 passed |
| `make test-functional` | PASS; 3 passed |
| `make test-failure` | PASS; 29 passed |
| `docker compose --env-file .env.example down -v --remove-orphans` | PASS; empty service state established |
| `docker compose --env-file .env.example build` | PASS; backend/bootstrap/UI images built |
| `docker compose --env-file .env.example up -d` | PASS; Mongo, replica-set init, bootstrap, Elasticsearch, Redis, API, and UI started |
| `SMOKE_DEADLINE_SECONDS=180 make smoke` | PASS; event `424a3410-fe49-4795-b0dd-b4090f9b590b` |
| `make postman` | PASS; 124 requests, 45 assertions, zero failures |
| `MONGO_URI=... ELASTICSEARCH_URL=... REDIS_URL=... make test-integration-required` | PASS; 13 passed, no skips |
| `MONGO_URI=... ELASTICSEARCH_URL=... REDIS_URL=... make test-acceptance-required` | PASS; 2 passed, no skips |
| `E2E_BASE_URL=... make test-e2e-required` | PASS; 1 passed |
| `PERF_BASE_URL=... PERF_REQUESTS=10 make performance` | PASS; 10/10 identities converged, zero errors |
| `PERF_BASE_URL=... make performance-load` | PASS; 500/500 identities converged, zero errors |
| `make coverage` | PASS; 467 passed, 91% branch coverage, 90% floor |
| `.venv/bin/pytest --collect-only -q` | PASS; 481 collected |
| `git diff --check` | PASS |

The 500-event run used concurrency 50, completed acceptance in 5.015 seconds at
99.70 events/second, and confirmed all accepted IDs through MongoDB and
Elasticsearch after 2.164 seconds of convergence. POST `/events` p95 was 507.78
ms. This is bounded assignment-scale evidence, not a production SLO claim.

## Smoke stages exercised

The clean smoke path verified:

- Mongo replica-set availability and deterministic index bootstrap;
- Elasticsearch and Redis availability;
- API liveness and readiness;
- `POST /events` returning `202`;
- background-worker persistence;
- canonical `GET /events` visibility;
- Elasticsearch projection and `GET /events/search` visibility;
- Mongo analytics through `GET /events/stats`;
- Redis-backed `GET /events/stats/realtime`.

## Queue scope

The local SQS-style queue remains intentionally in process because the assignment
explicitly requires a simulated in-process queue. Its at-least-once, visibility,
retry/backoff, DLQ, idempotency, bounded-admission, and graceful-drain semantics
are tested. Catastrophic process loss can still lose events resident only in that
queue; `docs/operations/sqs-migration.md` documents the production evolution path.
