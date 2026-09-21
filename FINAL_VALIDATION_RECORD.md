# Final Validation Record

Date: 2026-09-21

## Rebuild convergence invariant

Mongo `_id` is used only as `backfill_upper_bound` for the majority-consistent
historical scan. It is not a commit-order or convergence watermark. The rebuild
opens an independent change-stream cursor immediately after candidate
dual-write is enabled. After backfill, the cursor is drained and its latest
Mongo `clusterTime`, represented losslessly as `(seconds, increment)`, is
persisted as `source_fence`. The projector must persist a position at or after
that fence before verification and alias cutover. Resume tokens remain opaque
restart cursors and are never numerically compared.

For the preallocated ObjectId race, writer X can allocate `_id` before the
backfill bound and commit after the bounded scan. Because the candidate target
is already active, X is observed by the independent change stream and dual
written to the candidate. The source fence includes X's commit position, and
cutover waits for the projector to reach it. The service-backed acceptance test
asserts X's `_id` is below the bound, the scan indexes only A-C, X/D/E/F arrive
during the rebuild, and A-G are present through the stable alias after cutover.

## Integration fixes

The first complete integration run was 4 passed / 9 failed. The failures were
root-caused and fixed as follows:

- Replaced obsolete `AsyncDatabase.drop()` calls with the current client's
  `drop_database(name)` API in the integration cleanup helpers.
- Replaced removed Elasticsearch `ignore_status`/`ignore_unavailable` cleanup
  arguments with explicit 404 handling and concrete index resolution for
  wildcard cleanup.
- Derived the bootstrap assertion from the current storage manifest (13
  indexes), instead of the stale hard-coded count of 10.
- Added projector and persistence-worker startup readiness gating so the API
  cannot accept an event before the Mongo change-stream cursor is open.
- Corrected the realtime integration fixture to use a current rolling window.
- Kept Elasticsearch cursor pagination within one signed query scope.

## Exact validation commands and results

| Command | Result |
| --- | --- |
| `.venv/bin/ruff format --check src tests` | PASS, 130 files formatted |
| `.venv/bin/ruff check src tests` | PASS |
| `.venv/bin/mypy` | PASS, 59 source files |
| `.venv/bin/pytest -q tests/unit tests/failure` | PASS, 426 passed |
| `MONGO_URI=... ELASTICSEARCH_URL=... REDIS_URL=... .venv/bin/pytest -q tests/integration` | PASS, 13 passed |
| `MONGO_URI=... ELASTICSEARCH_URL=... .venv/bin/pytest -q tests/integration/test_rebuild_live.py` | PASS, 2 passed |
| `docker compose --env-file .env.example config --quiet` | PASS |
| `docker compose down -v --remove-orphans` | PASS, empty service state established |
| `docker compose build` | PASS |
| `docker compose up -d` | PASS, Mongo/Elasticsearch/Redis/API/UI healthy |
| `make smoke` | PASS, clean-stack event `9e2f40fe-e88c-43d7-b694-1932d233fd41` |
| `make smoke` after final rebuild | PASS, event `951c898b-176b-45a7-b69d-9058dc149bd6` |
| guarded `python -m event_platform.cli storage bootstrap` + `search rebuild --confirm` with unique DB/alias | PASS, durable completed record and atomic alias swap |
| `git diff --check` | PASS |

## Smoke stages exercised

The smoke script now verifies live and ready health, POST `/events`, canonical
Mongo-backed GET `/events`, Mongo analytics GET `/events/stats`, Elasticsearch
GET `/events/search`, and Redis-backed GET `/events/stats/realtime`.
