# Final Acceptance Checklist

## Architecture and semantics

- [ ] Mongo is demonstrably canonical.
- [ ] ES is demonstrably eventually consistent and rebuildable.
- [ ] Redis loss does not lose events.
- [ ] 202/local queue durability caveat is explicit.
- [ ] at-least-once + idempotency behavior is tested.
- [ ] no exactly-once claim appears anywhere.
- [ ] online ES rebuild works with live writes and atomic alias swap.
- [ ] rate limiting is implemented with Redis and local fallback.

## Required endpoints

- [ ] POST /events
- [ ] GET /events
- [ ] GET /events/stats
- [ ] GET /events/search
- [ ] GET /events/stats/realtime

## Operations

- [ ] liveness/readiness/component health
- [ ] metrics
- [ ] JSON logs and request IDs
- [ ] graceful shutdown
- [ ] retry/backoff/DLQ
- [ ] read-only ops status for reviewer UI

## Reviewer experience

- [ ] one-command Compose stack
- [ ] Mongo replica set initializes automatically
- [ ] UI is included and useful
- [ ] Postman collection/environment import cleanly
- [ ] Postman demo flow passes
- [ ] smoke test passes from clean stack

## Quality

- [ ] format
- [ ] lint
- [ ] static typing
- [ ] unit tests
- [ ] integration tests
- [ ] failure tests
- [ ] no Blocker/Critical review findings
- [ ] requirements traceability completed
- [ ] README and ARCHITECTURE match code
- [ ] AI workflow section is concrete/factual
