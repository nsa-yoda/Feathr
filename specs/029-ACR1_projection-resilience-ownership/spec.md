# Feature Specification: ACR1 Projection Resilience and Ownership

**Feature**: 029-ACR1_projection-resilience-ownership
**Status**: Draft
**Source findings**: ACR1-B P1-02, P1-03, P1-06, P3-03

## User Scenarios & Testing

### User Story 1 - Degrade search without stopping ingestion (Priority: P1)

An operator loses search connectivity and expects canonical queue admission and persistence to continue while projection health and lag become visibly degraded.

**Independent Test**: Exhaust projection retries while canonical ingestion remains healthy, then restore search and verify bounded catch-up.

### User Story 2 - Enforce one logical projection owner (Priority: P1)

When multiple service replicas exist, only the current fenced projection owner advances a checkpoint for a logical partition.

**Acceptance Scenarios**:

1. **Given** two projector candidates, **When** ownership changes, **Then** the stale owner cannot persist an older checkpoint.
2. **Given** a burst of projection events, **When** indexing runs, **Then** bounded batches preserve per-item retry and failure classification.

### Edge Cases

- Search recovers after the restart budget is exhausted.
- One item in a batch fails permanently while others succeed.
- Resume history is invalid for a documented driver error code.
- An unrecognized resume failure occurs without a stable error code.

## Functional Requirements

- **FR-001**: Projection failure MUST NOT stop canonical queue admission or persistence.
- **FR-002**: Projection MUST have independent degradable health, bounded restart/backoff, and lag reporting.
- **FR-003**: Each logical projector partition MUST have one fenced owner that alone can advance its checkpoint.
- **FR-004**: Checkpoint identity MUST be unique and stale generations MUST be rejected.
- **FR-005**: Projection writes MUST support bounded batching with per-item success, transient retry, and permanent failure handling.
- **FR-006**: Batch/concurrency limits MUST provide backpressure rather than unbounded task creation.
- **FR-007**: Invalid resume history MUST be classified primarily by stable driver codes/labels; any compatibility fallback MUST be narrowly bounded and tested.
- **FR-008**: Recovery tests MUST prove catch-up from a persisted checkpoint without duplicate serving records or checkpoint regression.

## Key Entities

- **Projection Ownership**: Logical partition, holder, fencing generation, and expiry.
- **Projection Batch**: Bounded events with item-level outcomes.
- **Projection Health**: State, retry budget, checkpoint, and canonical lag.

## Success Criteria

- **SC-001**: Canonical ingestion remains available throughout injected search outages.
- **SC-002**: No stale owner can regress a checkpoint in concurrent-owner tests.
- **SC-003**: Projection throughput is measured in bounded batches and item failures do not discard successful items.
- **SC-004**: Recovery reaches the canonical boundary within the configured catch-up objective.

## Assumptions and Scope

- Search documents remain idempotent by canonical event identity.
- Partitioned broker/CDC deployment may be implemented later; this feature must provide safe ownership for the current topology.
