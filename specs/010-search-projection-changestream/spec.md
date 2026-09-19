# Feature Specification: Mongo Change-Stream Search Projection

**Feature Branch**: `010-search-projection-changestream`  
**Created**: 2026-09-18  
**Status**: Accepted for implementation  
**Input**: `REQUEST.md`

## Clarifications

- The projector watches inserts from the canonical `events` collection. Updates and deletes are ignored because canonical events are immutable append-only records.
- One checkpoint document is stored in Mongo's operational database under a stable projector name. The resume token is stored in a BSON-safe form together with projection status, last-success time, last event timestamp, and a bounded diagnostic code.
- A missing checkpoint starts a new stream from the current change-stream position. An invalid or non-resumable existing token enters `reconciliation_required` and stops consumption; it never silently starts at `now`.
- The normal projection writes one Elasticsearch document through the stable alias using `event_id` as `_id`. Checkpoint persistence occurs only after every required write succeeds.
- Transient Elasticsearch or Mongo errors retain the checkpoint, emit a bounded retry state, and use injectable backoff. Permanent projection data errors enter a visible failed state without advancing the checkpoint.
- Feature 012 owns active rebuild metadata. When a rebuild target is supplied by that later feature, each live event is written to both the stable alias and target before checkpoint advancement; this feature exposes the dual-write seam without implementing rebuild orchestration.

## User Scenarios & Testing

### User Story 1 - Project a persisted event (Priority: P1)

As an operator, I need a canonical Mongo event to become an Elasticsearch document so search can catch up without changing ingestion durability.

**Independent Test**: Feed a representative insert change through a fake change stream and verify deterministic projection, `event_id` document identity, ES write completion, and checkpoint persistence order.

**Acceptance Scenarios**:

1. **Given** an insert change with a valid canonical event, **When** the projector handles it, **Then** it writes the projected document through the configured stable alias with the event ID as document ID and then persists the resume token.
2. **Given** the same change is replayed, **When** it is handled again, **Then** the same document ID is used and the operation remains idempotent.
3. **Given** the event cannot be decoded safely, **When** it is handled, **Then** no checkpoint is advanced and the projector exposes a bounded failure state.

### User Story 2 - Survive dependency failure (Priority: P1)

As an operator, I need Elasticsearch outages to stop checkpoint advancement without losing the Mongo change history.

**Independent Test**: Make ES fail transiently and verify the checkpoint remains unchanged, retry status/backoff is observable, and a later successful attempt projects the event.

**Acceptance Scenarios**:

1. **Given** Elasticsearch is unavailable, **When** the projector processes a change, **Then** it reports a transient degraded state, retains the prior checkpoint, and schedules bounded retry.
2. **Given** ES recovers, **When** retry runs, **Then** the event is written and the checkpoint advances only after success.
3. **Given** Mongo change-stream access fails, **When** the projector is running, **Then** it reports dependency failure and does not claim projection progress.

### User Story 3 - Resume and recover safely (Priority: P1)

As an operator, I need restarts and invalid resume history to be visible so history is not silently skipped.

**Independent Test**: Persist a valid checkpoint, restart and assert resume options; persist an invalid/non-resumable checkpoint and assert reconciliation-required state with no new stream from `now`.

**Acceptance Scenarios**:

1. **Given** a valid checkpoint, **When** the projector starts, **Then** it resumes from that token and exposes the previous success time and lag approximation.
2. **Given** no checkpoint exists, **When** the projector starts, **Then** it begins at the current stream position and records an initial status without fabricating historical progress.
3. **Given** a resume token is invalid or history is no longer available, **When** the stream is opened or resumed, **Then** the projector enters `reconciliation_required`, emits a structured state transition, and stops before consuming new events.

### User Story 4 - Support online rebuild dual writes (Priority: P2)

As a rebuild coordinator, I need live changes to reach the active target generation before the checkpoint moves.

**Independent Test**: Configure a target generation and verify alias and target writes both complete before checkpoint persistence; a target failure leaves the checkpoint unchanged.

**Acceptance Scenarios**:

1. **Given** an active target index, **When** a change is processed, **Then** the stable alias and target generation receive the same deterministic document before checkpoint advancement.
2. **Given** either required write fails, **When** the change is processed, **Then** the checkpoint is retained and the failure state is visible.

## Edge Cases

- Change events missing `operationType`, `fullDocument`, event ID, timestamp, or required fields are rejected safely without checkpoint advancement.
- Resume tokens must remain BSON-safe and must not be emitted in logs or API responses.
- ES acknowledgement, timeout, and connection errors are classified without exposing credentials, URLs containing credentials, request bodies, or raw driver messages.
- Lag is an approximation from the latest successfully projected event timestamp and current UTC time; absent timestamps produce an explicit unknown value.
- Cancellation and shutdown stop new stream consumption and leave the last successful checkpoint intact.

## Requirements

### Functional Requirements

- **FR-001**: The service MUST consume insert changes from the canonical Mongo events collection through an async change-stream boundary.
- **FR-002**: The service MUST deterministically project canonical event fields and use immutable `event_id` as the Elasticsearch document ID through a configured stable alias.
- **FR-003**: The service MUST persist a resume checkpoint only after all required Elasticsearch writes for that change succeed.
- **FR-004**: Replaying a change MUST be safe and target the same document ID without creating a second logical document.
- **FR-005**: Transient Mongo/Elasticsearch failures MUST retain the last checkpoint, expose degraded status, and use bounded injectable retry backoff.
- **FR-006**: Invalid, expired, or non-resumable existing checkpoints MUST enter `reconciliation_required` and MUST NOT silently start a new stream at the current position.
- **FR-007**: The projector MUST expose status including state, last-success time, approximate lag, failure code, and whether a checkpoint exists; sensitive tokens and raw driver details MUST be excluded.
- **FR-008**: A configured rebuild target MUST receive each live projection alongside the stable alias before checkpoint advancement; target failures MUST retain the checkpoint.
- **FR-009**: Shutdown and cancellation MUST stop new consumption and preserve the last successful checkpoint.
- **FR-010**: Tests MUST cover projection/checkpoint ordering, replay idempotency, ES outage, restart resume, invalid-token recovery, malformed events, retry behavior, and real MongoDB/Elasticsearch integration paths when services are available.

## Key Entities

- **ProjectionCheckpoint**: Stable projector name, BSON-safe resume token, status, updated time, last projected event timestamp, and bounded failure code.
- **ProjectionStatus**: Public operational snapshot containing state, checkpoint presence, last success, approximate lag, and safe failure code.
- **ProjectedEvent**: Deterministic Elasticsearch document source with canonical identity and fields required by later mapping/search features.
- **ChangeStreamEvent**: Insert operation plus full canonical document and resume token.

## Success Criteria

- **SC-001**: Every valid insert handled in the focused suite records the ES write before checkpoint persistence, with zero checkpoint advances on write failure.
- **SC-002**: Replaying 100% of a sample set of changes produces one stable document ID per event and no duplicate logical documents.
- **SC-003**: A restart with a valid checkpoint resumes from that checkpoint in all restart tests; invalid checkpoint tests enter reconciliation-required state without consuming new events.
- **SC-004**: Dependency failure tests show a retained checkpoint and safe degraded status within one bounded retry decision.
- **SC-005**: Real-service integration tests, when MongoDB and Elasticsearch are configured, prove change consumption, projection, and checkpoint persistence; unavailable services cause explicit skips rather than false passes.
- **SC-006**: The projector emits structured state transitions for startup, success, retry, invalid checkpoint, reconciliation required, and shutdown without sensitive payloads.

## Assumptions

- Feature 003's async Mongo repository remains the canonical event store and operational checkpoint store boundary.
- Feature 012 supplies rebuild target lifecycle metadata; this feature accepts an optional target writer but does not own alias swapping or bulk rebuild.
- The projector is a single process-local worker in the demo runtime; a later production evolution may use a durable stream and multiple consumers.
