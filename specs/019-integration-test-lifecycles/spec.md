# Feature Specification: Integration Test Lifecycles

**Feature Branch**: `019-integration-test-lifecycles`
**Created**: 2026-09-19
**Status**: Accepted
**Input**: `REQUEST.md`

## User Scenarios & Testing

### User Story 1 - Prove canonical ingestion and query (Priority: P1)

As a reviewer, I need a real MongoDB lifecycle that submits an event through the HTTP API, lets the asynchronous worker persist it, and reads it back through the canonical query API.

**Independent Test**: With real MongoDB configured, submit a unique event through the app, poll for its immutable ID in `GET /events`, and clean the unique database namespace.

**Acceptance Scenarios**

1. Given a reachable MongoDB replica set, when `POST /events` accepts a valid event, then the worker persists it and `GET /events` returns the same canonical event within a bounded deadline.
2. Given the worker receives the same event delivery twice, when both deliveries complete, then MongoDB contains one canonical document and the second delivery is classified as an idempotent duplicate.

### User Story 2 - Prove change-stream search projection (Priority: P1)

As a reviewer, I need a real MongoDB change stream and Elasticsearch projection lifecycle so that persisted metadata becomes searchable without coupling search success to ingestion acknowledgement.

**Independent Test**: With MongoDB replica-set and Elasticsearch endpoints configured, persist a uniquely named event, poll the search API for its metadata term, and remove the isolated indices/database afterward.

**Acceptance Scenarios**

1. Given reachable MongoDB and Elasticsearch, when a canonical event is persisted, then the change-stream projector writes the stable search alias and `GET /events/search` finds the metadata term.
2. Given projection processing is eventually consistent, when search is polled before visibility, then the test waits with a bounded deadline and reports the last observed response on timeout.

### User Story 3 - Prove real aggregation and cache lifecycles (Priority: P1)

As a reviewer, I need real MongoDB aggregation and Redis cache behavior so that grouped statistics and cache-aside semantics are validated across service boundaries.

**Independent Test**: Seed a unique MongoDB namespace, call the statistics/realtime APIs, and assert grouping, miss-to-hit transition, logical result equality, TTL, and cleanup.

**Acceptance Scenarios**

1. Given events across types and UTC bucket boundaries, when the stats API runs, then the real MongoDB grouping returns the expected inclusive hour/day/week counts.
2. Given a populated MongoDB collection and empty Redis key, when realtime stats are requested twice, then the first response is a miss, the second is a hit, both results are logically equal, and the cache key has bounded TTL.

### User Story 4 - Prove online rebuild and live search continuity (Priority: P1)

As a reviewer, I need an online Elasticsearch rebuild lifecycle that uses MongoDB as its source, swaps an alias atomically, and preserves searchability for prior data.

**Independent Test**: Seed prior events, run the real rebuild, assert alias generation and counts, add a live event through the projection path, and verify both prior and live terms remain searchable.

**Acceptance Scenarios**

1. Given a serving alias and canonical Mongo events, when rebuild completes, then the alias points to a verified generation whose count matches the source.
2. Given a live event arrives after rebuild activation, when the change-stream projector catches up, then the prior and live events are searchable through the serving alias.

## Edge Cases

- Missing or unreachable service endpoints cause explicit integration skips with the required environment name, never a false pass.
- Poll deadlines include the operation, namespace, and last observed state; no unbounded loop or fixed long sleep is allowed.
- Each test uses unique database, collection, alias, index, cache-key, and projector namespaces and deletes them in `finally` cleanup.
- A MongoDB endpoint without replica-set/change-stream support is reported as unavailable for projection scenarios.
- Elasticsearch and Redis clients are closed even when setup, polling, or assertions fail.
- Repeated test execution cannot reuse stale aliases, checkpoints, documents, or Redis keys.

## Requirements

### Functional Requirements

- **FR-001**: Integration tests MUST use real MongoDB, Elasticsearch, and Redis clients for the scenarios that depend on them; fakes and mocks cannot satisfy the lifecycle assertions.
- **FR-002**: The harness MUST provide unique namespaces, deterministic setup, bounded poll-until helpers with diagnostic timeout errors, and unconditional cleanup/async client closure.
- **FR-003**: A real app lifecycle test MUST prove `POST /events` -> persistence worker -> MongoDB -> `GET /events` with the same canonical event ID and payload.
- **FR-004**: A real MongoDB replica-set change stream and Elasticsearch lifecycle MUST prove persisted metadata reaches the search API through the serving alias.
- **FR-005**: Real MongoDB aggregation MUST prove grouped statistics for seeded event types and UTC time buckets.
- **FR-006**: Real MongoDB and Redis MUST prove realtime cache miss then hit, equal logical result, bounded TTL, and isolated key cleanup.
- **FR-007**: Real online rebuild MUST prove source/target counts, verified alias generation, and search continuity for prior and live events.
- **FR-008**: Integration failures MUST include actionable service/namespace context and must not leak credentials, full event metadata, or raw dependency errors.
- **FR-009**: The integration command and README/testing documentation MUST state required environment variables, service-gated skip behavior, and the exact scenarios covered.
- **FR-010**: The application lifecycle MUST expose the configured Elasticsearch search service to the search route when the real client is created, and MUST release it during shutdown.

## Key Entities

- **IntegrationNamespace**: Unique database, collection, alias, index, checkpoint, and cache-key prefix allocated for one test.
- **PollObservation**: Operation name, monotonic deadline, interval, attempt count, and last safe observation used in timeout diagnostics.
- **ServiceHarness**: Real MongoDB, Elasticsearch, and Redis clients plus cleanup ownership for one lifecycle test.

## Success Criteria

- **SC-001**: All six requested lifecycle scenarios have at least one real-service test with observable assertions and unique cleanup.
- **SC-002**: The integration suite contains no unbounded polling and no synchronization based on a fixed multi-second sleep.
- **SC-003**: When required services are available, each scenario completes or fails with an actionable bounded diagnostic; when unavailable, it emits an explicit service-gated skip naming the missing endpoint.
- **SC-004**: Re-running the same integration selection three times with fresh namespaces leaves no stale test documents, aliases, indices, checkpoints, or Redis keys.
- **SC-005**: The full repository unit, failure, and static gates remain green after the harness and lifecycle wiring changes.

## Assumptions

- Feature 021 owns the one-command Docker Compose reviewer stack; Feature 019 consumes service endpoints and does not duplicate Compose orchestration.
- `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL` are the integration harness inputs; service-gated tests skip when a required input is absent or unreachable.
- Integration tests may use the repository's existing async clients and pytest fixtures, but every scenario must exercise the real dependency boundary.
- Search visibility and change-stream delivery are eventually consistent and are asserted with bounded polling.
