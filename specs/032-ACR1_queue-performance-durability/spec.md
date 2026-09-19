# Feature Specification: ACR1 Queue Performance and Durability

**Feature**: `032-ACR1_queue-performance-durability`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P2-003; AUTO_CODE_REVIEW_1_B P0-04, P1-07

## User Scenarios & Testing

### User Story 1 - Keep the local queue responsive at its configured cap (Priority: P1)

As a developer or reviewer, I can exercise large local backlogs without queue operations degrading through repeated full scans.

**Independent Test**: Benchmark send, receive, visibility change, and delete operations at the configured maximum backlog.

**Acceptance Scenarios**:

1. **Given** a backlog at the supported cap, **When** messages become visible or expire, **Then** hot-path work scales with the affected messages rather than the full queue.
2. **Given** repeated visibility changes and deletes, **When** receipts become stale, **Then** they cannot mutate a later delivery.

### User Story 2 - Deploy with durable delivery semantics (Priority: P1)

As a production operator, I can select a durable queue adapter so accepted events and dead-letter records survive process or host loss.

**Acceptance Scenarios**:

1. **Given** a production deployment, **When** the API acknowledges an accepted event and the application restarts, **Then** the event remains deliverable.
2. **Given** a permanently failed message, **When** retry policy is exhausted, **Then** its dead-letter record is durably inspectable and replayable.
3. **Given** local demo mode, **When** the in-process adapter is selected, **Then** documentation and health output clearly report its volatile guarantee.

## Edge Cases

- Many messages share the same visibility deadline.
- A receipt is deleted after visibility timeout and redelivery.
- The durable broker is unavailable during admission.
- A deployment changes queue adapters while messages remain outstanding.
- Dead-letter replay races with an existing delivery.

## Functional Requirements

- **FR-001**: The local queue MUST maintain indexed ready and in-flight scheduling so normal hot-path operations do not scan the full backlog.
- **FR-002**: Receipt generations MUST prevent stale delete or visibility operations from affecting a later delivery.
- **FR-003**: Deterministic clocks and benchmarks MUST cover maximum configured backlog and visibility-expiry bursts.
- **FR-004**: Queue metrics MUST expose ready, delayed, in-flight, expired, retried, and dead-letter counts without high-cardinality labels.
- **FR-005**: A production queue adapter MUST durably retain accepted messages across application and host restarts.
- **FR-006**: Production dead-letter records MUST be durable, inspectable, and replayable with an audit trail.
- **FR-007**: Adapter capabilities MUST declare whether `202 Accepted` means durable acceptance or volatile local acceptance.
- **FR-008**: Production startup MUST reject a volatile adapter unless an explicit non-production override is active.
- **FR-009**: Adapter migration and drain procedures MUST prevent silent loss or duplicate acknowledgement.
- **FR-010**: The current in-process SQS-like adapter MUST remain available for deterministic local development and tests.

## Key Entities

- **Queue Adapter Capability**: Durability, acknowledgement, visibility, dead-letter, and replay guarantees.
- **Delivery Record**: Message identity, generation, visibility deadline, attempts, and receipt state.
- **Dead-Letter Record**: Failed message reference, disposition, failure class, and replay history.

## Success Criteria

- **SC-001**: Queue benchmarks show no linear full-backlog scan in send, delete, or ordinary receive operations.
- **SC-002**: Restart tests prove acknowledged production messages and dead-letter records survive process loss.
- **SC-003**: Health and documentation identify the active adapter and its durability guarantee.
- **SC-004**: Stale-receipt tests cannot delete or extend a redelivered message.

## Assumptions and Scope

- The durable adapter is a production evolution; this spec does not rewrite the accepted local demo queue contract.
- Broker product selection belongs in the implementation plan and ADR.
