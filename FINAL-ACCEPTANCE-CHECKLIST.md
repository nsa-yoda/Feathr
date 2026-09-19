# Final Acceptance Checklist

## Architecture and semantics

- [x] Mongo is demonstrably canonical.
- [x] ES is demonstrably eventually consistent and rebuildable.
- [x] Redis loss does not lose events.
- [x] 202/local queue durability caveat is explicit.
- [x] at-least-once + idempotency behavior is tested.
- [x] no positive exactly-once guarantee appears anywhere; negative limitation wording is retained.
- [ ] online ES rebuild works with live writes and atomic alias swap (service-backed lifecycle evidence remains required).
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

Static, unit, failure, and contract evidence is checked in the feature reports and `CODEX_WORK.LOG`. Integration selection currently records 11 explicit skips because the test runner is not configured with direct external endpoint variables; this is not service-backed integration evidence. Clean Compose smoke and the Postman demo are verified on the local Colima context. The online rebuild remains unchecked until its live-write and atomic-alias-swap scenario is run.
