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
- [x] Postman demo flow passes (124 requests and 45 assertions via repository-pinned Newman 6.2.2)
- [x] smoke test passes from clean empty-volume stack (Colima Docker context)

## Quality

- [x] format
- [x] lint
- [x] static typing
- [x] unit tests
- [x] required service-backed integration suite (13 passed, no skips)
- [x] failure tests
- [x] no Blocker/Critical review findings
- [x] requirements traceability completed
- [x] README and ARCHITECTURE match code
- [x] AI workflow section is concrete/factual

## Evidence conditions

Static, unit, failure, and contract evidence is checked in the quality report and
`CODEX_WORK.LOG`. On 2026-09-21 the repository was reset to empty Compose volumes,
built, and started before the smoke, Postman, complete integration, rebuild
acceptance, E2E, stable performance, and 500-event load gates were executed. The
integration suite passed 13 tests with no skips. The dedicated rebuild acceptance
passed 2 tests: it deterministically held backfill, inserted live writes during
candidate dual-write, proved source-fence/projector convergence and identity
coverage, observed one atomic alias swap, verified post-cutover writes, and covered
verification, alias-swap, and post-swap persistence failures. The bounded load run
accepted 500 unique events and reconciled every event ID through MongoDB and
Elasticsearch before passing. Exact commands and results are recorded in
`FINAL_VALIDATION_RECORD.md` and `QUALITY-GATES-REPORT.md`.
