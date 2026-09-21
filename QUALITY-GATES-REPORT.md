# Quality Gates Report

## 1. Test layers implemented

The repository now has explicit, registered pytest layers and local commands:

| Layer | Location / command | Purpose |
|---|---|---|
| Unit | `tests/unit`, `make test-unit` | Isolated domain, queue, lifecycle, storage, projection, CLI, and configuration semantics |
| Functional | `tests/functional`, `make test-functional` | HTTP routing, middleware, validation, problem responses, OpenAPI, and accepted ingestion |
| Failure | `tests/failure`, `make test-failure` | Deterministic dependency outages, retries, ownership loss, and recovery |
| Integration | `tests/integration`, `make test-integration-required` | Real MongoDB replica set, Elasticsearch, Redis, change streams, bootstrap, analytics, and projection |
| Acceptance | `tests/integration/test_rebuild_live.py`, `make test-acceptance-required` | Online rebuild, live writes, convergence, fencing, verification, and atomic alias cutover |
| E2E | `tests/e2e`, `make test-e2e-required` | Black-box HTTP ingestion, idempotency, canonical query, search, stats, and realtime lifecycle |
| Performance | `scripts/performance`, `make performance` | Bounded HTTP regression probe with p50/p95/p99, throughput sample, and error count |
| Smoke | `scripts/smoke`, `make smoke` | Clean Compose readiness and critical event lifecycle |
| Release | `.github/workflows/release.yml`, `make release-verify` | Tagged-version quality, Docker build, archive, metadata, and checksums |

Markers are strict and registered for `unit`, `functional`, `integration`,
`acceptance`, `e2e`, `failure`, `performance`, `smoke`, `security`, and `release`.

## 2. Test counts and coverage

- Baseline before structural changes (`a47a81d` verification baseline): 397 unit,
  29 failure, and 13 dependency-optional integration cases collected; `make all`
  passed.
- Current local backend run: **441 tests passed** across unit, functional, and
  failure selections, including the process lifecycle test.
- Service-backed integration: **13 passed**, with no skips in the required gate.
- Online rebuild acceptance: **2 passed**, with no skips.
- Black-box E2E: **1 passed** against the clean Compose stack.
- Branch-aware backend coverage: **85% baseline to 90% current**, enforced by
  `make coverage` with a 90% floor. The report includes unit, functional, and
  failure tests and writes `coverage/coverage.xml`.

The remaining uncovered code is concentrated in dependency-specific lifecycle
branches that require a live failure or cancellation at an exact network boundary:
`main.py` (80%), `search/rebuild_runtime.py` (54%), `search/rebuild.py` (85%),
`search/projection.py` (85%), and `storage/change_stream.py` (80%). These are
covered by real integration/acceptance gates where possible; the remaining lines
are cleanup, transport-exception, or process-cancellation branches that cannot be
meaningfully exercised by a deterministic local unit test without replacing the
service boundary. No broad `no cover` exclusions were added.

## 3. Integration, E2E, and acceptance results

The clean service run used empty Compose volumes and current pinned services:

1. `docker compose down -v --remove-orphans`
2. `docker compose build`
3. `docker compose up -d`
4. `make smoke` — passed ingestion, Mongo persistence/query, Elasticsearch search,
   Mongo stats, and Redis realtime stats.
5. `make test-integration-required` — 13 passed.
6. `make test-acceptance-required` — 2 passed, including online rebuild live-write
   convergence and failure-boundary evidence.
7. `make test-e2e-required` — 1 passed.

The E2E test uses a current UTC event timestamp so the realtime window assertion
tests the intended contract instead of a stale fixture.

## 4. Performance baseline

`PERF_BASE_URL=http://127.0.0.1:8000 PERF_REQUESTS=10 make performance` passed with
zero errors. Recorded p95 latency was:

| Route | p50 | p95 | p99 |
|---|---:|---:|---:|
| POST `/events` | 9.87 ms | 13.18 ms | 13.18 ms |
| GET `/events` | 49.87 ms | 53.27 ms | 53.27 ms |
| GET `/events/stats` | 200.79 ms | 208.84 ms | 208.84 ms |
| GET `/events/search` | 200.10 ms | 227.17 ms | 227.17 ms |
| GET `/events/stats/realtime` | 199.38 ms | 203.29 ms | 203.29 ms |

The probe is intentionally a stable sanity gate rather than a production load
benchmark. Larger scheduled load tests should be added when a representative CI
runner and traffic profile are selected.

## 5. CI workflows and gates

`.github/workflows/ci.yml` now has:

- a fast quality job for locked installation, formatting, Ruff, MyPy, dependency
  consistency, source-archive hygiene, unit/functional/failure tests, coverage,
  and diff checks;
- a service job that resets Compose, runs smoke, required integration and
  acceptance suites, E2E, and performance, then uploads Compose logs and results;
- a Docker job for Compose validation and production image builds;
- least-privilege read permissions, concurrency cancellation, timeouts, locked
  dependency caching, and failure artifact capture.

The required gates do not use `continue-on-error` and fail on skipped cases in
service-backed suites.

## 6. Release/tag behavior and artifacts

`.github/workflows/release.yml` runs for `v*.*.*` tags (and manual dispatch),
repeats static/unit/failure/coverage and Compose/Docker validation, then emits:

- `coverage/coverage.xml`;
- `artifacts/release/BUILD-METADATA.json` containing version, Git SHA, and UTC build time;
- a versioned `git archive` source tarball;
- `SHA256SUMS` for release files.

The workflow does not claim an SBOM unless a future release environment supplies a
trusted SBOM generator. Adding one is a release-tooling task, not a silent CI skip.

## 7. Exact validation commands and results

Passed:

```text
make format-check                 (native .venv equivalent: PASS)
make lint                         (native .venv equivalent: PASS)
make typecheck                    PASS
make dependency-check             uv lock --check + uv pip check: PASS
git diff --check                  PASS
.venv/bin/pytest -q tests/unit tests/functional tests/failure  441 passed
.venv/bin/coverage ...            90%, fail-under=90, coverage.xml written
docker compose config             PASS
docker compose down -v ...        PASS
docker compose build              PASS
docker compose up -d              PASS
make smoke                        PASS
make test-integration-required    13 passed
make test-acceptance-required     2 passed
make test-e2e-required            1 passed
make performance                  PASS, zero errors
```

The repository `uv run` wrapper could not use the host's default uv cache in the
restricted shell, so static commands were executed with the locked `.venv`
equivalents; `uv lock --check` and `uv pip check` were also run directly and
passed. `make postman` remains environment-dependent because Newman is not
installed in this workspace; the repository script reports that missing tool with
nonzero status rather than hiding it. The Postman collection remains a separate
reviewer gate.

## 8. Deliberately deferred work and trigger

- **Heavy load testing:** add a scheduled/manual Locust or k6 profile when a
  representative runner and target throughput/SLO are agreed; the lightweight
  probe already protects against obvious regressions.
- **SBOM generation:** add Syft or Docker SBOM generation when the release
  environment standardizes the approved generator and artifact schema.
- **Automated dependency vulnerability scanning:** add a pinned scanner when the
  project selects an advisory database policy; lock consistency and image/build
  validation are enforced now.
- **Browser UI E2E:** add Playwright only when UI behavior becomes a release
  acceptance contract; the current required black-box API flows cover the
  backend guarantees and the static UI remains smoke-tested through Compose.
