# Feature Specification: ACR1 Lifecycle and Delivery Safety

**Feature**: 027-ACR1_lifecycle-delivery-safety
**Status**: Draft
**Source findings**: ACR1-A P1-003; ACR1-B P0-02, P1-04, P2-09

## User Scenarios & Testing

### User Story 1 - Drain accepted work before shutdown (Priority: P1)

An operator terminates the service and expects new admission to stop while already accepted events receive a bounded opportunity to reach canonical persistence before shared resources close.

**Independent Test**: Begin shutdown with queued and in-flight events, including cancellation-resistant work, and verify the documented disposition of every event and task.

**Acceptance Scenarios**:

1. **Given** accepted queue entries, **When** graceful shutdown begins, **Then** admission stops first and accepted work drains within the configured deadline.
2. **Given** a task remains alive after cancellation, **When** its deadline expires, **Then** shared resources it can still access are not reported as safely closed.

### User Story 2 - Preserve delivery ownership during slow persistence (Priority: P1)

A worker processing longer than the visibility interval retains or safely loses delivery ownership without crashing the consumer or acknowledging work it no longer owns.

### Edge Cases

- A task suppresses cancellation or shields dependency I/O.
- A visibility extension fails after canonical persistence succeeds.
- Another consumer receives the message before the first consumer disposes it.
- A zero or dangerously short visibility timeout is configured.

## Functional Requirements

- **FR-001**: Shutdown MUST stop new queue admission before worker drain begins.
- **FR-002**: Every accepted message MUST end shutdown as persisted and acknowledged, visibly pending for restart semantics, or explicitly recorded with a safe incomplete disposition.
- **FR-003**: Shared clients MUST close only after owned tasks have terminated or have been isolated by an explicit fail-fast policy.
- **FR-004**: Long-running processing MUST renew delivery visibility with margin or enforce a measured upper processing bound below visibility expiry.
- **FR-005**: Stale receipt handles MUST be classified as delivery-ownership loss and MUST NOT crash the worker lifecycle.
- **FR-006**: Task registration MUST declare critical, restartable, or degradable policy with bounded restart/backoff behavior.
- **FR-007**: Production settings MUST reject zero visibility timeout.
- **FR-008**: Logs and metrics MUST expose drain duration, incomplete work, visibility renewals, ownership loss, and cancellation timeout.

## Key Entities

- **Task Policy**: Criticality, restart budget, cancellation deadline, and health effect.
- **Delivery Ownership**: Message, receipt generation, visibility deadline, and renewal state.
- **Shutdown Disposition**: Final state of accepted work at process termination.

## Success Criteria

- **SC-001**: Graceful shutdown tests account for 100% of accepted messages.
- **SC-002**: No shared resource closes while a task that may use it remains unisolated.
- **SC-003**: Persistence beyond one visibility interval causes no unhandled worker exception.
- **SC-004**: Degradable task failure does not stop critical canonical persistence.

## Assumptions and Scope

- The current queue remains volatile and single-process until the durable-queue feature is implemented.
- Bounded shutdown may still terminate with incomplete work; the disposition must be explicit and truthful.
