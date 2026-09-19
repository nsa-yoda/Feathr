# Feature Specification: ACR1 Rebuild Convergence and Operations

**Feature**: 028-ACR1_rebuild-convergence-operations
**Status**: Draft
**Source findings**: ACR1-A P1-002, P2-001; ACR1-B P1-12, P1-13, P2-01, P2-10, P2-11

## User Scenarios & Testing

### User Story 1 - Cut over only after proven convergence (Priority: P1)

An operator rebuilds the search projection while events continue arriving and expects the candidate to match a defined canonical boundary before the serving alias changes.

**Independent Test**: Insert events during activation and scan, delay projection, and verify every boundary event is present before cutover.

**Acceptance Scenarios**:

1. **Given** concurrent canonical writes, **When** a rebuild scans and catches up, **Then** the candidate proves convergence to a persisted source boundary before swap.
2. **Given** alias swap succeeds but completion-state persistence fails, **When** recovery runs, **Then** the live target is never deleted and state is reconciled.

### User Story 2 - Operate and inspect rebuilds end to end (Priority: P1)

An operator can start the supported rebuild command, inspect current or historical status by identifier, and distinguish lease ownership, progress, failure, and reconciliation states.

### Edge Cases

- Lease expires during a slow batch or verification step.
- Cardinality matches while identifiers or sampled hashes differ.
- Lock creation succeeds but status persistence fails.
- A stale coordinator attempts swap after a newer lease holder takes ownership.

## Functional Requirements

- **FR-001**: Each rebuild MUST persist a canonical high-water boundary and the projector checkpoint observed for cutover.
- **FR-002**: Cutover MUST require projector convergence plus count and bounded identity/content verification; count equality alone is insufficient.
- **FR-003**: Lease ownership MUST use periodic renewal and a monotonically increasing fencing value enforced on state transitions and cutover.
- **FR-004**: Alias swap MUST be a commit barrier after which cleanup cannot delete the serving target.
- **FR-005**: Post-swap metadata failure MUST enter a recoverable reconciliation state rather than generic rollback.
- **FR-006**: Lease and status records MUST have deliberate authority boundaries and cannot silently diverge.
- **FR-007**: Runtime startup MUST wire rebuild status storage and the supported command MUST construct the same dependency graph as the service.
- **FR-008**: Status lookup MUST retrieve current and historical rebuilds by identifier.
- **FR-009**: Tests MUST cover concurrent writes, expired/stale coordinators, post-swap state failure, wrong-document equal-count candidates, and historical lookup.

## Key Entities

- **Rebuild Boundary**: Canonical high-water marker and required projector checkpoint.
- **Fenced Lease**: Holder, expiry, and monotonically increasing generation.
- **Rebuild Record**: Progress, verification evidence, cutover state, and reconciliation outcome.

## Success Criteria

- **SC-001**: No tested concurrent write is absent from the serving index after a successful rebuild.
- **SC-002**: A stale lease holder cannot swap or mutate committed state.
- **SC-003**: The serving alias target survives every injected post-swap persistence failure.
- **SC-004**: Supported status and command paths work in the normal configured runtime without permanent 503 or parser-only behavior.

## Assumptions and Scope

- Canonical events are append-only for this feature.
- Search remains derived and rebuildable; canonical ingestion must not depend on rebuild availability.
