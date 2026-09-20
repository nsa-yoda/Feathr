# Testing Strategy

## Philosophy

Test externally meaningful semantics and failure recovery. Avoid maximizing line coverage at the expense of confidence.

## Unit tests

Cover pure/isolated behavior:

- event validation/normalization and payload hashing;
- cursor encoding/decoding;
- queue visibility/receipt semantics with an injectable clock;
- retry classification/backoff/jitter bounds;
- idempotency equivalence/conflict decisions;
- metadata flattening for ES;
- cache key construction;
- rate-limit token math/local fallback;
- problem response mapping.

## Integration tests with real dependencies

Use real MongoDB replica set, Elasticsearch, and Redis. Required lifecycles include:

1. ingest -> worker -> Mongo query returns event;
2. ingest -> Mongo -> Change Stream projector -> ES metadata search returns event;
3. seed events -> stats aggregation returns expected bucket/type counts;
4. realtime stats miss -> cached hit; Redis outage -> Mongo bypass still succeeds;
5. duplicate/redelivery -> one canonical event;
6. ES rebuild -> alias swap -> search remains correct.

Use bounded eventually/poll helpers, not arbitrary sleeps.

## Failure-path tests

At minimum demonstrate:

- Mongo unavailable -> worker retry/backoff -> DLQ/queue behavior and readiness impact;
- worker failure after Mongo insert before ack -> redelivery is idempotent;
- ES unavailable -> ingestion/Mongo reads continue, search degrades, checkpoint does not skip;
- Redis unavailable -> cache bypass + local rate limiter fallback;
- queue full -> POST returns 503;
- leaky-bucket queued release -> success, while full admission backlog -> 429 and retry headers;
- invalid cursor/query/input -> stable 4xx problem documents.

Feature 020 adds deterministic failure-injection coverage for the complete
outage and recovery boundaries. The current failure gate contains 29 passing
tests and uses manual clocks, finite failure counters, typed fake ports, and
immediate awaitable sleeps. It proves no false acknowledgement during Mongo
failure, unhealthy readiness, deterministic queue 503, post-insert redelivery
idempotency, one-entry DLQ exhaustion, Elasticsearch checkpoint retention and
recovery, invalid-resume reconciliation, Redis cache/rate-limit fallback, and
serving-alias safety after rebuild failure. These tests do not claim real
service outage behavior; Feature 019's integration selection owns real MongoDB,
Elasticsearch, and Redis lifecycle evidence.

## Coverage

Use coverage reporting as a signal, not the sole acceptance metric. Critical queue/idempotency/retry/rate-limit modules should have especially high branch coverage. Run `make coverage` to execute the locked unit suite, print line and branch coverage, and write `coverage/coverage.xml`. The ACR2 unit gate contains 388 tests and enforces a 90% terminal threshold. This result is a snapshot of the isolated unit suite and does not replace semantic review, integration, failure, browser, Compose, or Postman evidence.

## Integration lifecycle evidence

Feature 019 integration tests use real MongoDB, Elasticsearch, and Redis clients. Set `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL` for the scenarios under test; MongoDB projection scenarios require a replica set. The suite uses unique namespaces, bounded monotonic polling with timeout diagnostics, and unconditional cleanup. Missing or unreachable services are explicitly skipped and remain separate from green service-backed evidence.
