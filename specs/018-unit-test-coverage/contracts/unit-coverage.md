# Unit Coverage Contract

## Focused semantic suite

Feature 018's focused selection uses deterministic unit tests for queue and worker state transitions, retry and idempotency outcomes, query/search/analytics validation, cache behavior, rate-limit identity/math, and settings/problem boundaries. It must run without external services or wall-clock sleeps.

## Coverage report command

`make coverage` runs the isolated `tests/unit` suite against `src/event_platform` with the locked development dependencies, prints a terminal report, and writes `coverage/coverage.xml`. The command may be extended by Feature 024's CI workflow but remains locally reproducible here.

Coverage is evidence of executed lines/branches only. It does not prove semantic completeness, integration with MongoDB/Elasticsearch/Redis, queue timing under production load, browser behavior, Compose startup, or Postman flows.
