# Feature Specification: Failure Injection and Recovery Tests

**Feature Branch**: `020-failure-injection-tests`
**Created**: 2026-09-19
**Status**: Accepted
**Input**: `REQUEST.md`

## User Scenarios & Testing

### User Story 1 - Protect canonical ingestion during Mongo failure (Priority: P1)

As an operator, I need deterministic proof that a MongoDB outage causes bounded retries and visible unhealthy readiness while preserving the queue message for recovery.

**Why this priority**: MongoDB is canonical truth. A false acknowledgement or silent readiness success can lose events and mislead operators.

**Independent Test**: Inject a failing canonical store behind a real in-process queue, run one worker attempt with a deterministic clock, inspect retry visibility and readiness, then recover the store and prove the message is persisted and removed exactly once.

**Acceptance Scenarios**:

1. **Given** Mongo persistence is unavailable, **When** the worker processes a delivery, **Then** it schedules bounded visibility retry, does not acknowledge or remove the message, and the readiness snapshot reports Mongo and the persistence worker unhealthy.
2. **Given** the canonical store recovers before retry exhaustion, **When** the delivery becomes visible again, **Then** the worker persists the event and acknowledges it without a false earlier success.
3. **Given** the queue has no available capacity, **When** an ingestion request attempts admission, **Then** the request receives deterministic 503 problem semantics and no event is reported as accepted.

### User Story 2 - Prove redelivery idempotency and retry disposition (Priority: P1)

As an operator, I need proof that a failure after canonical insertion but before acknowledgement is safe to redeliver and that exhausted retries reach the dead-letter queue once.

**Why this priority**: At-least-once delivery is expected. Duplicate canonical records or repeated DLQ entries would corrupt reviewer confidence and operational recovery.

**Independent Test**: Use a deterministic store and queue clock, inject an acknowledgement failure after a successful insert, redeliver the same immutable event, and separately exhaust a transient failure sequence while inspecting canonical count, source disposition, and DLQ entries.

**Acceptance Scenarios**:

1. **Given** an event was inserted before acknowledgement failed, **When** the same delivery is redelivered, **Then** same-payload idempotency removes the delivery without creating a second canonical record.
2. **Given** transient persistence failure continues through the configured receive limit, **When** the final attempt is processed, **Then** exactly one DLQ entry is created, the source delivery is removed, and the reason is an allowlisted operational code.

### User Story 3 - Keep Mongo useful and projection state safe during ES failure (Priority: P1)

As a reviewer, I need proof that Elasticsearch outage does not block canonical ingestion or query, and that projection recovery resumes from the last durable checkpoint.

**Why this priority**: Elasticsearch is derived and rebuildable; losing or advancing a checkpoint during an outage can permanently skip search updates.

**Independent Test**: Inject an ES writer outage while using deterministic canonical and checkpoint fakes, assert Mongo-side operations continue, then restore the writer and consume the retained change. Inject an invalid resume history and verify reconciliation is required before opening a new stream.

**Acceptance Scenarios**:

1. **Given** Elasticsearch is unavailable, **When** canonical ingestion and query run, **Then** they succeed independently while search returns a safe 503 and the projection checkpoint remains unchanged.
2. **Given** Elasticsearch recovers, **When** the retained change is replayed, **Then** the document is written and the checkpoint advances to that change exactly once.
3. **Given** a stored checkpoint or resume token is stale/invalid, **When** projection starts, **Then** status is `reconciliation_required` with a safe recovery code and the source does not silently start at the latest event.

### User Story 4 - Keep the service usable during Redis failure (Priority: P1)

As an operator, I need proof that Redis is disposable: realtime statistics bypass the cache to canonical Mongo and rate limiting falls back to a local conservative policy.

**Why this priority**: Redis outages must degrade derived acceleration, not make core reads unusable or disable request protection.

**Independent Test**: Inject deterministic Redis failures into the cache and rate-limit ports, then assert a canonical realtime result, `BYPASS` outcome, local backend decision, and stable HTTP behavior.

**Acceptance Scenarios**:

1. **Given** Redis cache reads and writes fail, **When** realtime statistics are requested, **Then** Mongo computes the result, the response identifies a bypass, and no raw Redis error is exposed.
2. **Given** Redis token consumption fails, **When** a protected route is checked, **Then** the local bucket decides with conservative limits and remains usable.

### User Story 5 - Keep rebuild aliases safe on failure (Priority: P1)

As an operator, I need proof that a failed Elasticsearch rebuild cannot move the serving alias to an unverified or bad generation.

**Why this priority**: The serving alias is the search availability boundary; an unsafe swap can make every search request observe incomplete data.

**Independent Test**: Inject a deterministic target indexing, verification, or alias-swap failure into the rebuild port, then inspect the durable failed record, serving alias, and cleanup calls.

**Acceptance Scenarios**:

1. **Given** a rebuild target fails before verification or alias swap, **When** the rebuild exits, **Then** the serving alias remains on the old index and the failed target is eligible for cleanup.
2. **Given** alias swap itself fails, **When** the failure is recorded, **Then** no completed record is emitted and the old serving alias remains authoritative.

## Edge Cases

- Retry delays, clocks, and receive counts are deterministic and bounded; tests do not sleep on wall-clock time or depend on random network failures.
- A failed retry or DLQ operation leaves the source delivery available for operator recovery rather than silently dropping it.
- A malformed or stale resume token produces reconciliation status and never opens a latest-only stream.
- Redis cache corruption and Redis transport errors both use the canonical bypass path.
- Queue saturation and readiness failures use safe problem/health contracts without raw dependency details.
- Failure assertions do not log credentials, request bodies, full event metadata, or dependency exception text.

## Requirements

### Functional Requirements

- **FR-001**: The failure suite MUST use explicit deterministic dependency seams or test doubles for Mongo, Elasticsearch, Redis, queue, checkpoint, and rebuild failures.
- **FR-002**: Mongo outage coverage MUST prove bounded worker retry, no acknowledgement before persistence, unhealthy readiness, and recovery without false acceptance.
- **FR-003**: Queue saturation coverage MUST prove a deterministic HTTP 503 problem response and no queue admission success.
- **FR-004**: Redelivery coverage MUST prove same-payload idempotency creates one canonical record after a post-insert/pre-ack failure.
- **FR-005**: Retry exhaustion coverage MUST prove one source disposition and exactly one allowlisted DLQ entry relative to that disposition.
- **FR-006**: Elasticsearch outage coverage MUST prove canonical Mongo ingestion/query remain usable, search maps to safe 503, and projection checkpoints do not advance until the write succeeds.
- **FR-007**: Projection recovery coverage MUST prove a recovered writer catches up from the retained change and stale/invalid resume history reports reconciliation instead of silently starting latest.
- **FR-008**: Redis outage coverage MUST prove realtime cache bypass and conservative local rate-limit fallback keep the service usable without raw Redis details.
- **FR-009**: Rebuild failure coverage MUST prove an unverified target cannot move the serving alias and failed target cleanup/state recording remain observable.
- **FR-010**: Failure tests MUST be isolated, bounded, repeatable, and independent of external service availability or OS-level network chaos.
- **FR-011**: Failure test diagnostics and documentation MUST preserve the project's safe structured logging and no-secret/no-full-payload rules.
- **FR-012**: Traceability and workflow records MUST report exact current test counts and distinguish deterministic failure evidence from real-service integration evidence.

## Key Entities

- **Fault seam**: An explicit injectable port or deterministic test double that changes one dependency outcome without altering production defaults.
- **Delivery disposition**: The observable outcome for one queue delivery: acknowledged/removed, visibility retry, or one DLQ move.
- **Projection checkpoint**: The last resume token durably saved after a successful derived write.
- **Rebuild record**: Durable state for a target generation, including failed/completed phase, counts, and bounded failure codes.
- **Failure evidence**: A test result with the injected fault, expected invariant, observed disposition, and safe diagnostic context.

## Success Criteria

### Measurable Outcomes

- **SC-001**: The Feature 020 failure selection contains deterministic tests for all five user stories and passes with no external MongoDB, Elasticsearch, or Redis endpoints.
- **SC-002**: Every requested failure invariant has at least one assertion covering both the failure disposition and the recovery or safety invariant; no scenario is represented only by a no-exception assertion.
- **SC-003**: Queue saturation, retry exhaustion, stale checkpoint, and rebuild failure tests complete within bounded test time without fixed sleeps or nondeterministic network behavior.
- **SC-004**: The full failure suite passes in the repository gate, and its exact count is recorded in traceability, the AI workflow log, and this feature's review report.
- **SC-005**: Review finds zero open blocker findings and no unqualified warning affecting canonical truth, acknowledgement semantics, checkpoint safety, fallback usability, or alias safety.

## Assumptions

- MongoDB remains canonical; Elasticsearch and Redis remain derived/non-authoritative as established by the constitution and prior features.
- Existing production ports and safe error codes are the preferred seams; Feature 020 adds test evidence and only minimal production corrections if a required invariant is actually absent.
- Real-service lifecycle availability remains Feature 019 evidence and is not replaced by deterministic failure tests.
- Feature 021 owns Docker Compose orchestration and full-stack startup; this feature consumes no external service by default.
