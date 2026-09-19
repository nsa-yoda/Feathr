# Feature Specification: ACR1 Analytics and Cache Scalability

**Feature**: `033-ACR1_analytics-cache-scalability`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P2-004; AUTO_CODE_REVIEW_1_B P1-08, P1-09, P2-04

## User Scenarios & Testing

### User Story 1 - Query analytics at sustained volume (Priority: P1)

As a dashboard user, I receive bounded-latency statistics without repeatedly scanning the raw event collection.

**Independent Test**: Load a production-scale fixture, query common windows, and verify the bounded read plan uses maintained rollups.

**Acceptance Scenarios**:

1. **Given** maintained hourly and daily rollups, **When** a supported statistics window is requested, **Then** the response is assembled from bounded rollup reads.
2. **Given** late or corrected events, **When** reconciliation runs, **Then** affected rollups converge without double counting.
3. **Given** a forensic request, **When** raw recomputation is explicitly selected, **Then** it remains bounded and distinguishable from the normal path.

### User Story 2 - Share cache work safely (Priority: P1)

As a client, I do not trigger duplicate expensive computations during cache misses, and one cancelled request does not cancel work needed by others.

**Acceptance Scenarios**:

1. **Given** concurrent misses for one cache key on one process, **When** one caller disconnects, **Then** remaining callers can still receive the shared result.
2. **Given** concurrent misses across replicas, **When** coordination is available, **Then** one bounded computation refreshes the key and others wait or receive documented stale data.
3. **Given** coordination failure, **When** fallback activates, **Then** work remains bounded and the degraded state is observable.

## Edge Cases

- Late events arrive after a rollup bucket was finalized.
- A rollup rebuild overlaps incremental updates.
- The cache leader fails while computing a value.
- All waiters cancel before shared work completes.
- A stale value is older than the permitted serving window.

## Functional Requirements

- **FR-001**: Supported production analytics queries MUST use maintained rollups or another bounded materialized representation.
- **FR-002**: Rollup updates MUST be idempotent and correct under retries, late events, and reconciliation.
- **FR-003**: Operators MUST be able to rebuild and verify rollups from canonical Mongo data.
- **FR-004**: Raw-event analytics MUST be an explicit bounded path with limits, metrics, and operational warnings.
- **FR-005**: Cache miss coalescing MUST prevent duplicate same-key work within a process.
- **FR-006**: Cancellation by one waiter MUST NOT cancel shared work while other waiters remain.
- **FR-007**: Multi-replica deployments MUST coordinate expensive same-key refreshes or use a documented bounded fallback.
- **FR-008**: Stale-while-revalidate behavior, if enabled, MUST define maximum staleness and failure handling.
- **FR-009**: Metrics MUST report rollup lag, raw fallback use, cache hit state, coalesced waiters, refresh duration, and coordination failures.
- **FR-010**: Index design and slow-query evidence MUST be reviewed against actual analytics workloads before release.

## Key Entities

- **Rollup Bucket**: Time interval, grouping dimensions, aggregates, watermark, and version.
- **Refresh Lease**: Bounded ownership for a distributed cache refresh.
- **Shared Computation**: In-process work and waiter lifecycle for a cache key.

## Success Criteria

- **SC-001**: Normal analytics latency remains within the documented target as raw event volume grows by an order of magnitude.
- **SC-002**: Rebuild comparison finds no unexplained difference between rollups and canonical events.
- **SC-003**: A concurrent miss test performs at most one computation per process and one coordinated refresh per key across replicas.
- **SC-004**: Cancellation tests prove remaining waiters receive the result.

## Assumptions and Scope

- Mongo remains canonical; rollups and cache entries are rebuildable derived data.
- Exact latency and data-volume targets are fixed in the implementation plan using measured deployment capacity.
