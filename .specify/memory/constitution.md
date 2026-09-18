# Distributed Event Processing Platform Constitution

**Version:** 1.0.0  
**Ratified:** 2026-09-18  
**Status:** Governing — non-negotiable unless intentionally amended

## I. Truth, projections, and consistency

1. MongoDB **MUST** be the canonical system of record for accepted events.
2. Elasticsearch **MUST** be treated as a derived, rebuildable search projection. Search is eventually consistent by design.
3. Redis **MUST NOT** hold the only copy of business-critical state. Realtime cache entries may expire or disappear without event loss.
4. No code path may claim a distributed transaction exists across MongoDB, Elasticsearch, and Redis.
5. Derived stores **MUST** be reconstructable from canonical state, and rebuild/recovery actions **MUST** be observable.

## II. Queue semantics are explicit

1. The demo ingestion queue **MUST** model SQS-style receive/delete semantics with visibility timeout and receipt handles.
2. Delivery is **at least once while the process is alive**, not exactly once.
3. The in-process queue is volatile. `202 Accepted` **MUST NOT** be documented as crash-durable acceptance.
4. A worker **MUST NOT** delete/acknowledge a message until canonical persistence succeeds or an equivalent idempotent replay is verified.
5. Retry count, retry classification, backoff, jitter, visibility behavior, DLQ transition, capacity behavior, and shutdown behavior **MUST** be specified and tested.

## III. Idempotency before "exactly once"

1. The system **MUST** assume duplicate delivery can occur.
2. Every accepted event **MUST** have an immutable `event_id`.
3. MongoDB **MUST** enforce uniqueness of `event_id`.
4. Replaying the same event identity with the same payload **MUST** be safe.
5. A duplicate identity associated with materially different content **MUST** be treated as a conflict/corruption signal, not silently overwritten.
6. The architecture **MUST NOT** advertise exactly-once processing.

## IV. Fail independently and degrade deliberately

1. MongoDB unavailability may stall persistence and eventually fill the local queue, but must not cause false success in the worker.
2. Elasticsearch unavailability **MUST NOT** cause loss of Mongo-persisted events.
3. Redis unavailability **MUST NOT** cause event loss or total rate-limit bypass; cache requests fall back to Mongo and rate limiting falls back to a conservative local limiter.
4. Degraded modes **MUST** be represented in logs, metrics, and component health.
5. Retry only errors classified as transient. Permanent validation/data errors **MUST NOT** be retried indefinitely.

## V. Security and abuse resistance by default

1. Rate limiting is mandatory on externally exposed application endpoints except explicitly documented health probes.
2. Request body size, metadata size/depth, string lengths, page size, query length, and date-range limits **MUST** be bounded.
3. Forwarded client IP headers **MUST NOT** be trusted unless trusted proxy configuration enables them.
4. Secrets **MUST** come from configuration/environment, never source code.
5. Application containers **MUST** run as non-root where feasible.
6. Logging **MUST** avoid credentials and full arbitrary metadata payloads.
7. CORS **MUST** be explicit and narrow for the demo UI.

## VI. Async correctness and lifecycle ownership

1. FastAPI async request handlers **MUST NOT** call blocking network clients.
2. Use PyMongo's Async API and Elasticsearch's async client.
3. Long-lived clients, background workers, change streams, and queue tasks **MUST** be created and closed through deterministic lifespan management.
4. SIGTERM/SIGINT shutdown **MUST** stop new receives, allow bounded completion of in-flight work, close clients, and emit shutdown state.
5. Because the queue is process-local, the demo **MUST** run a single API process. Horizontal scaling is a documented SQS-era evolution, not a fake local guarantee.

## VII. Observable operations

1. Logs **MUST** be structured JSON in service runtime.
2. Every request **MUST** have a request/correlation ID; generated IDs must be returned to callers.
3. Important background operations **MUST** have operation IDs (e.g. `rebuild_id`).
4. Prometheus-compatible metrics **MUST** cover HTTP traffic, queue depth, retries, DLQ, worker processing, Mongo persistence, ES projection lag/failures, cache outcomes, and rate limiting.
5. Liveness, readiness, and component-health semantics **MUST** be distinct and documented.
6. Operationally significant state transitions **MUST** be logged once with enough context to reconstruct what occurred.

## VIII. Testing proves semantics, not implementation shape

1. Every feature **MUST** include meaningful tests for business behavior and error paths.
2. Queue tests **MUST** cover visibility timeout/redelivery, retry scheduling, DLQ, capacity, and worker crash-equivalent behavior.
3. Integration tests **MUST** use real MongoDB, Elasticsearch, and Redis services.
4. End-to-end tests **MUST** cover at least two complete lifecycles; this project targets more than the minimum.
5. Failure tests **MUST** demonstrate graceful behavior when MongoDB, Elasticsearch, and Redis are unavailable.
6. Tests **MUST NOT** depend on arbitrary sleeps when deterministic polling, fake clocks, or bounded eventual assertions are possible.

## IX. Spec-first change discipline

1. Every implementation feature **MUST** originate from a Spec Kit feature request.
2. Clarification **MUST** resolve semantics before implementation when ambiguity affects guarantees.
3. `spec.md`, `plan.md`, and `tasks.md` **MUST** remain consistent; run analyze before implementation and converge after.
4. A change to a locked architectural decision **MUST** produce an ADR supersession.
5. Review findings with Blocker/Critical severity **MUST** be fixed before acceptance.

## X. Reviewer experience matters, but backend integrity wins

1. Docker Compose **MUST** provide a one-command reviewer environment.
2. A Postman collection **MUST** be executable as an acceptance/demo suite.
3. A lightweight UI **MUST** make ingestion, querying, search, analytics, cache behavior, and service status easy to demonstrate.
4. UI work **MUST NOT** delay or weaken backend correctness, testing, failure semantics, or documentation.

## XI. Simplicity with production intent

1. Do not introduce infrastructure the assessment does not require merely to appear sophisticated.
2. Prefer the smallest design that faithfully demonstrates production principles.
3. Production evolutions (real SQS, independent worker fleet, sharding, materialized analytics, managed Elastic, multi-region) belong in architecture/scaling notes unless required for correctness now.
4. Code should be readable and maintainable by a team; avoid unnecessary factories, inheritance hierarchies, and abstract frameworks.

## Amendment rule

Amendments require a clearly described motivation, version bump, affected ADR/spec updates, and a review of consequences. Silent constitutional drift is prohibited.
