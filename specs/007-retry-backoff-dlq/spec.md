# Feature Specification: Retry, Backoff, and Simulated DLQ

**Feature Branch**: `007-retry-backoff-dlq`

**Created**: 2026-09-18

**Status**: Accepted for implementation

**Input**: Feature request in `REQUEST.md`: make every persistence-processing failure disposition explicit.

## User Scenarios & Testing

### User Story 1 - Retry transient persistence failures (Priority: P1)

As an operator, I need temporary dependency failures to be retried without holding a worker slot so that recoverable events eventually reach canonical storage.

**Why this priority**: Mongo/network failures are expected operational conditions and must not create false acknowledgements or silently lose queue messages.

**Independent Test**: Inject a transient persistence failure, inspect the message visibility deadline and retry metric, advance a deterministic clock, then process successfully without an in-process sleep.

**Acceptance Scenarios**:

1. **Given** a delivery received for the first time, **When** persistence returns a transient dependency error, **Then** the source message remains queued, its visibility is changed to a bounded exponential delay, and the retry count increases.
2. **Given** a transient failure followed by a healthy dependency, **When** the scheduled delivery becomes visible, **Then** the event is persisted once and the current receipt is acknowledged.
3. **Given** repeated transient failures, **When** the configured receive limit is reached, **Then** the delivery is moved to the DLQ and is removed from the source queue.

### User Story 2 - Dispose permanent and conflicting deliveries (Priority: P1)

As an operator, I need invalid data and immutable-ID conflicts to stop retrying and retain safe diagnostic context for investigation.

**Why this priority**: Retrying permanent failures wastes capacity and can create an unbounded poison-message loop.

**Independent Test**: Submit an invalid envelope and a conflicting event identity, then verify each produces one DLQ entry with no source-message ghost.

**Acceptance Scenarios**:

1. **Given** a malformed canonical envelope, **When** a worker receives it, **Then** the source message is moved directly to the DLQ with a safe permanent classification.
2. **Given** an existing event ID with a different payload hash, **When** no conflict disposition hook accepts it, **Then** the source message is moved to the DLQ without overwriting the canonical event.
3. **Given** a conflicting event and an explicit disposition hook that accepts the decision, **When** the hook completes successfully, **Then** the source delivery is acknowledged and no duplicate canonical record is created.

### User Story 3 - Observe queue failure state (Priority: P2)

As a reviewer, I need retry, DLQ, and queue-age state to be visible without exposing arbitrary event metadata in logs.

**Why this priority**: Operators must distinguish healthy backlog, delayed retries, and exhausted poison messages during a demo or incident.

**Independent Test**: Enqueue messages at known clock times, receive and delay them, and verify queue statistics and structured-safe DLQ diagnostics.

**Acceptance Scenarios**:

1. **Given** visible and in-flight messages with known enqueue times, **When** queue statistics are requested, **Then** depth, visibility, in-flight count, DLQ depth, and oldest age are reported deterministically.
2. **Given** a DLQ transition, **When** an operator inspects the DLQ entry, **Then** it contains the immutable envelope and bounded diagnostic fields such as classification, reason code, and attempt count, without raw exception text.

## Edge Cases

- The first receive is attempt 1; a configured maximum of 1 therefore DLQs on the first failure.
- Base delay, cap, jitter ratio, and maximum receives must be positive and bounded; calculated visibility delay cannot be negative or exceed the cap.
- A retry must not use `asyncio.sleep` while holding worker capacity.
- A permanent failure must not be retried even when receive capacity remains.
- An unknown exception receives conservative bounded retries, then DLQ disposition; it must never retry forever.
- A stale receipt or closed queue during disposition must not cause a false acknowledgement.
- The DLQ is volatile in this demo and is not a durable replacement for AWS SQS redrive storage.

## Requirements

### Functional Requirements

- **FR-001**: The worker MUST classify processing failures as transient, permanent, or unknown using safe reason codes.
- **FR-002**: The worker MUST schedule transient retries by changing message visibility rather than sleeping while holding worker capacity.
- **FR-003**: Backoff MUST be exponential from a configurable base, bounded by a configurable cap, and include bounded injectable jitter.
- **FR-004**: The system MUST count the first receive as attempt 1 and enforce a configurable maximum receive count with a default of 5.
- **FR-005**: Permanent failures and exhausted transient/unknown failures MUST move one copy of the envelope to the simulated DLQ before removing the source message.
- **FR-006**: A failed DLQ disposition MUST leave the source message available for later handling; the worker MUST NOT silently acknowledge it.
- **FR-007**: DLQ diagnostics MUST include only bounded safe fields: message identity, classification, reason code, and attempt count; raw exception text and arbitrary metadata MUST NOT be logged as diagnostics.
- **FR-008**: Queue statistics MUST expose queue depth, visible count, in-flight count, DLQ depth, and oldest queued age.
- **FR-009**: The worker MUST expose retry and DLQ counters suitable for later metrics wiring.
- **FR-010**: Tests MUST cover deterministic jitter/backoff bounds, transient recovery, permanent no-retry behavior, exhaustion, DLQ source removal, and no-source-ghost behavior.

### Key Entities

- **RetryPolicy**: Bounded base/cap/jitter/max-receive settings and deterministic delay calculation.
- **FailureDisposition**: A safe classification and reason code for one processing failure.
- **DeadLetter**: The original immutable delivery plus bounded diagnostic fields retained in the volatile DLQ.
- **QueueStats**: Current capacity, depth, visibility, in-flight, DLQ depth, and oldest age.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of injected transient failures in deterministic tests either recover and persist or reach the configured DLQ limit; none are acknowledged before persistence.
- **SC-002**: 100% of malformed and conflicting deliveries in deterministic tests receive a permanent DLQ disposition without overwriting canonical data.
- **SC-003**: Every calculated retry delay is within `[0, cap]`, and no retry test holds a worker execution slot during the delay.
- **SC-004**: The focused Feature 007 test suite covers at least 8 behavior-level cases and the full existing unit suite remains green.
- **SC-005**: DLQ diagnostics contain no raw exception message and no arbitrary metadata field beyond the immutable envelope itself.

## Assumptions

- Feature 004 owns the in-process queue and remains the source of visibility, receipt, and volatile DLQ state.
- Feature 006 owns canonical persistence and duplicate equivalence checks; Feature 007 adds failure disposition around that worker.
- A future lifecycle/observability feature will wire worker counters and queue age into Prometheus and component health.
- AWS SQS redrive is documented as the production evolution; this feature does not add external infrastructure.

