# Quality Gates Report

Last verified: 2026-09-21

## 1. Test layers implemented

| Layer | Location / command | Purpose |
|---|---|---|
| Unit | `tests/unit`, `make test-unit` | Domain, queue, lifecycle, storage, projection, CLI, configuration, and tooling semantics |
| Functional | `tests/functional`, `make test-functional` | HTTP routing, middleware, validation, errors, OpenAPI, and accepted ingestion |
| Failure | `tests/failure`, `make test-failure` | Deterministic outages, retries, ownership loss, and recovery |
| Integration | `tests/integration`, `make test-integration-required` | Real MongoDB replica set, Elasticsearch, Redis, change streams, bootstrap, analytics, and projection |
| Acceptance | `tests/integration/test_rebuild_live.py`, `make test-acceptance-required` | Online rebuild, live writes, convergence, fencing, identity verification, and atomic alias cutover |
| E2E | `tests/e2e`, `make test-e2e-required` | Black-box HTTP ingestion, idempotency, Mongo query, search, stats, and realtime lifecycle |
| Postman | `postman`, `make postman` | Reviewer API contract and demo flow through repository-pinned Newman 6.2.2 |
| Performance sanity | `scripts/performance`, `make performance` | Stable latency, throughput, error-rate, and convergence gate |
| Bounded load | `scripts/performance`, `make performance-load` | 500-event concurrent ingestion plus Mongo/Elasticsearch identity reconciliation |
| Smoke | `scripts/smoke`, `make smoke` | Clean Compose readiness and critical event lifecycle |
| Release | `.github/workflows/release.yml`, `make release-verify` | Tagged-version quality, Docker build, archive, metadata, and checksums |

Pytest markers are strict and registered for `unit`, `functional`, `integration`,
`acceptance`, `e2e`, `failure`, `performance`, `smoke`, `security`, and `release`.

## 2. Current counts and coverage

- Complete repository collection: **481 tests**.
- Branch-aware backend coverage selection: **467 passed** across unit, functional,
  and failure tests.
- Backend coverage: **91%**, enforced by `make coverage` with a **90% minimum**.
- Required service-backed integration: **13 passed**, no skips.
- Online rebuild acceptance: **2 passed**, no skips.
- Black-box E2E: **1 passed**.
- Repository-managed Postman: **124 requests and 45 assertions passed**.

Coverage measures `src/event_platform` with branch tracking and writes
`coverage/coverage.xml`. The remaining 393 uncovered statements and 154 partial
branches are concentrated in exact transport cancellation/failure timing and
dependency-specific lifecycle branches. Those risks are also exercised through
real-service integration, acceptance, smoke, and failure gates. No broad coverage
exclusions or threshold reductions were used.

## 3. Clean service-backed validation

The current run started from empty Compose volumes:

1. `docker compose --env-file .env.example down -v --remove-orphans`
2. `docker compose --env-file .env.example build`
3. `docker compose --env-file .env.example up -d`
4. `SMOKE_DEADLINE_SECONDS=180 make smoke` — passed for event
   `424a3410-fe49-4795-b0dd-b4090f9b590b`.
5. `make postman` — 124 requests, 45 assertions, zero failures.
6. `make test-integration-required` — 13 passed.
7. `make test-acceptance-required` — 2 passed.
8. `make test-e2e-required` — 1 passed.

The smoke lifecycle verified liveness, readiness, Mongo bootstrap, accepted
ingestion, async worker persistence, canonical query, Mongo analytics,
Elasticsearch projection/search, and Redis realtime statistics.

## 4. Performance evidence

### Stable CI profile

`PERF_REQUESTS=10 make performance` passed with zero errors, all 10 accepted IDs
visible in MongoDB and Elasticsearch, 67.98 accepted events/second, and 0.296
seconds to end-to-end convergence.

| Route | p50 | p95 | p99 |
|---|---:|---:|---:|
| POST `/events` | 13.60 ms | 22.26 ms | 22.26 ms |
| GET `/events` | 50.07 ms | 53.21 ms | 53.21 ms |
| GET `/events/stats` | 199.60 ms | 217.75 ms | 217.75 ms |
| GET `/events/search` | 194.23 ms | 214.83 ms | 214.83 ms |
| GET `/events/stats/realtime` | 198.78 ms | 206.15 ms | 206.15 ms |

### Bounded load profile

`make performance-load` sent 500 unique events with concurrency 50. All 500 were
accepted, persisted, and found by exact event identity through both the canonical
Mongo query and Elasticsearch search. The run completed ingestion in 5.015
seconds at 99.70 accepted events/second, reached full derived-state convergence
in 2.164 additional seconds, and recorded zero errors across 600 measured HTTP
requests. POST `/events` p95 was 507.78 ms; read-route p95 values were between
51.54 ms and 211.57 ms.

This is meaningful assignment-scale regression evidence for the required
in-process queue. It is not a production capacity or SLO claim. Production
capacity thresholds require representative deployment hardware, traffic shape,
and an agreed service objective; the documented SQS migration path remains a
future production evolution, not a replacement for the assignment queue.

## 5. CI and release gates

`.github/workflows/ci.yml` enforces locked installation, formatting, Ruff, MyPy,
dependency consistency, archive hygiene, unit/functional/failure tests, branch
coverage, Compose configuration, clean smoke, required integration, rebuild
acceptance, E2E, repository-managed Postman, stable performance, and Docker builds.
Required gates do not use `continue-on-error` or convert skips into success.

`.github/workflows/performance.yml` runs the 500-event profile weekly and on
demand, uploads the JSON result and Compose logs, and always tears down volumes.

Tags matching `v*.*.*` run `.github/workflows/release.yml`, which repeats the
mandatory gates and the bounded load profile before emitting:

- `coverage/coverage.xml`;
- `artifacts/performance.json` and `artifacts/performance-load.json`;
- `artifacts/release/BUILD-METADATA.json` with version, Git SHA, and UTC build time;
- a versioned source archive and SHA-256 checksums;
- Compose logs.

## 6. Exact latest commands and results

```text
make format-check                                                PASS, 142 files
make lint                                                        PASS
make typecheck                                                   PASS, 60 source files
make dependency-check                                            PASS
make check-source-archive                                        PASS
make compose-config                                               PASS
make test-unit                                                   PASS, 435 tests
make test-functional                                             PASS, 3 tests
make test-failure                                                PASS, 29 tests
docker compose --env-file .env.example down -v --remove-orphans   PASS
docker compose --env-file .env.example build                      PASS
docker compose --env-file .env.example up -d                      PASS
SMOKE_DEADLINE_SECONDS=180 make smoke                             PASS
make postman                                                     PASS, 124 requests / 45 assertions
make test-integration-required                                   PASS, 13 tests
make test-acceptance-required                                    PASS, 2 tests
make test-e2e-required                                           PASS, 1 test
PERF_REQUESTS=10 make performance                                PASS, 0 errors
make performance-load                                            PASS, 500/500 converged, 0 errors
make coverage                                                    PASS, 467 tests, 91%, floor 90%
.venv/bin/pytest --collect-only -q                               PASS, 481 collected
git diff --check                                                 PASS
```

Static, type, dependency, archive, Compose configuration, and diff checks are
rerun before every commit that updates this record.

## 7. Deliberate future trigger

The bounded load profile closes the repository's assignment-scale performance
evidence gap. A sustained multi-host production capacity program should be added
only when target hardware, workload distribution, and SLOs exist; at that point
it should include soak duration, resource saturation, and durable-queue testing.
That future program does not change the assignment's explicit requirement for a
simulated in-process queue in this repository.
