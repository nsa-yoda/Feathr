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
- rate limit exceeded -> 429 and retry headers;
- invalid cursor/query/input -> stable 4xx problem documents.

## Coverage

Use coverage reporting as a signal, not the sole acceptance metric. Critical queue/idempotency/retry/rate-limit modules should have especially high branch coverage. Run `make coverage` to execute the locked unit suite, print line and branch coverage, and write `coverage/coverage.xml`. In the socket-capable Feature 018 run, 282 unit tests passed; the XML report measured 3,323 statements at 87.9% line coverage and 844 branches at 75.5% branch coverage (the terminal combined score was 85%). This result is a snapshot of the isolated unit suite and does not replace semantic review, integration, failure, browser, Compose, or Postman evidence.
