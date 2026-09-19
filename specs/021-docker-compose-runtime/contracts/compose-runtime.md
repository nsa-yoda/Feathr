# Compose Runtime Contract

## Required services

`app`, `mongo`, `mongo-init`, `elasticsearch`, `redis`, and `ui` must exist. Long-running services expose health checks. `app` depends on successful `mongo-init` completion plus healthy Elasticsearch and Redis. `ui` depends on healthy `app`.

## Ports

- API: host `8000` to container `8000`
- UI: host `3000` to container `8080`
- Mongo, Elasticsearch, and Redis are reachable on the Compose network; host exposure is optional and disabled by default.

## Smoke contract

`scripts/smoke` must accept `SMOKE_DEADLINE_SECONDS` (default 90), use a unique `Idempotency-Key`, and check HTTP 200/202 responses for liveness, readiness, ingest, canonical query, search, and realtime stats. It must return nonzero on deadline or response mismatch.
