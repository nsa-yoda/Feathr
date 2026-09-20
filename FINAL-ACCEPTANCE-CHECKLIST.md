# Final Acceptance Checklist

## Architecture and semantics

- [x] Mongo is demonstrably canonical.
- [x] ES is demonstrably eventually consistent and rebuildable.
- [x] Redis loss does not lose events.
- [x] 202/local queue durability caveat is explicit.
- [x] at-least-once + idempotency behavior is tested.
- [x] no positive exactly-once guarantee appears anywhere; negative limitation wording is retained.
- [x] online ES rebuild works with live writes and atomic alias swap (service-backed lifecycle evidence recorded below).
- [x] rate limiting is implemented with Redis and local fallback.

## Required endpoints

- [x] POST /events
- [x] GET /events
- [x] GET /events/stats
- [x] GET /events/search
- [x] GET /events/stats/realtime

## Operations

- [x] liveness/readiness/component health
- [x] metrics
- [x] JSON logs and request IDs
- [x] graceful shutdown
- [x] retry/backoff/DLQ
- [x] read-only ops status for reviewer UI

## Reviewer experience

- [x] one-command Compose stack
- [x] Mongo replica set initializes automatically
- [x] UI is included and useful
- [x] Postman collection/environment import cleanly
- [x] Postman demo flow passes (205 requests and 45 assertions via ephemeral Newman on Colima)
- [x] smoke test passes from clean stack (Colima Docker context)

## Quality

- [x] format
- [x] lint
- [x] static typing
- [x] unit tests
- [x] integration test selection (11 explicit service-gated skips without endpoints; live execution remains required)
- [x] failure tests
- [x] no Blocker/Critical review findings
- [x] requirements traceability completed
- [x] README and ARCHITECTURE match code
- [x] AI workflow section is concrete/factual

## Evidence conditions

Static, unit, failure, and contract evidence is checked in the feature reports and `CODEX_WORK.LOG`. The dedicated service-backed rebuild acceptance was executed on 2026-09-20 against the Compose MongoDB replica set and Elasticsearch using `MONGO_URI='mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true' ELASTICSEARCH_URL='http://127.0.0.1:9200' .venv/bin/pytest -q tests/integration/test_rebuild_live.py`: 2 passed. It deterministically held the backfill, inserted D/E/F during candidate dual-write, proved high-water/projector convergence and identity coverage, observed one atomic alias swap, inserted G after cutover, and passed verification, alias-swap, and post-swap persistence failure cases. The executable guarded CLI was also run against a uniquely isolated real Mongo/Elasticsearch namespace and completed successfully. The checklist item is checked only on this evidence; the broader integration collection still has unrelated legacy cleanup/API compatibility failures documented in `CODEX_WORK.LOG`.
