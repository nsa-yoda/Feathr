# Feature Specification: Online Elasticsearch Rebuild

**Feature Branch**: `012-elasticsearch-online-rebuild`
**Created**: 2026-09-19
**Status**: Accepted for implementation
**Input**: `REQUEST.md`

## Clarifications

- Rebuild state and leases are stored in a dedicated Mongo operational collection; canonical events remain the only business source of truth.
- A lease is owner-bound, expires after a bounded duration, and may be acquired by a later run after expiry without changing the serving alias.
- Live dual-write target activation is an explicit callback into the Feature 010 projector; activation happens before the bulk scan and is cleared on every terminal path.
- Bulk failures are classified as transient or permanent. Transient failures receive bounded retries; any unresolved failure prevents alias swap.
- Verification requires zero unresolved failures, a target count no lower than the scanned canonical count, persisted backfill-bound/change-stream-position convergence, and identity reconciliation for every canonical event through the scan bound. The old generation is retained until a configured rollback deadline.
- The reviewer CLI exposes status and a guarded rebuild command contract; the HTTP API remains read-only for rebuild status.

## User Scenarios & Testing

### User Story 1 - Acquire and track a rebuild (Priority: P1)

As an operator, I need an exclusive leased rebuild record so concurrent runs cannot swap different targets.

**Independent Test**: Acquire a lease, reject a live competing owner, recover an expired lease, and assert every phase transition and safe state record.

### User Story 2 - Build and verify a target (Priority: P1)

As an operator, I need canonical Mongo events bulk-indexed into a new mapped generation while live changes dual-write to it.

**Independent Test**: Run a fake source and Elasticsearch client through create, activation, bulk retry, reconciliation, and verification; assert live writes are active before scanning.

### User Story 3 - Swap safely and retain rollback (Priority: P1)

As an operator, I need an atomic alias swap only after verification and retained old generation metadata for rollback.

**Independent Test**: Verify successful atomic swap and completion; inject failure and prove the old alias remains serving and target is never swapped.

### User Story 4 - Inspect operational status (Priority: P2)

As a reviewer, I need a read-only status endpoint and documented CLI command to inspect rebuild state without triggering a dangerous action.

**Independent Test**: Assert status output is safe and CLI help documents status/rebuild guard semantics.

## Edge Cases

- Missing alias, stale lease, empty source, transient bulk failure, permanent bulk failure, count mismatch, verification failure, cancellation, and cleanup failure.
- Rebuild IDs, owner IDs, index names, failure messages, and progress counters are bounded; document bodies are never logged.
- A failed run clears live target activation but retains the failed record and leaves the serving alias unchanged.

## Requirements

- **FR-001**: The service MUST persist a rebuild record with rebuild ID, phase, timestamps, source collection, old/target indexes, counts, failures, owner, and lease expiry.
- **FR-002**: The service MUST acquire an exclusive owner-bound lease and allow recovery only after expiry.
- **FR-003**: The service MUST create the next versioned physical index with the Feature 011 mapping/settings before activation.
- **FR-004**: The service MUST activate live dual-write before scanning canonical Mongo and clear it on all terminal paths.
- **FR-005**: The service MUST bulk-index canonical events with bounded transient retries and safe failure recording.
- **FR-006**: The service MUST capture a majority-consistent canonical backfill bound, use the ordered change-stream position as the convergence watermark, verify target count is not below the canonical scan count, and identity-reconcile every canonical event through the backfill bound with zero unresolved failures before swapping.
- **FR-007**: The service MUST atomically remove the old alias target and add the new target in one aliases operation.
- **FR-008**: The service MUST retain the old generation until a configured rollback deadline and never swap a failed/unverified target.
- **FR-009**: The service MUST expose read-only rebuild status and a documented guarded CLI command; no unprotected rebuild HTTP action is allowed.
- **FR-010**: Tests MUST cover success with writes during a deterministic backfill barrier, backfill-bound/change-stream-position convergence, identity verification, atomic alias behavior, post-cutover projection, alias failure safety, stale lease recovery, count/failure verification, status, and executable CLI behavior.

## Key Entities

- **RebuildRecord**: Durable operational state and progress.
- **RebuildLease**: Owner and expiry controlling exclusive execution.
- **RebuildFailure**: Bounded failure category and count.
- **RebuildStatus**: Read-only API projection.

## Success Criteria

- **SC-001**: Competing live owners cannot run or swap simultaneously; expired leases recover deterministically.
- **SC-002**: Live dual-write is active before the first bulk batch in every successful run.
- **SC-003**: Failed or unverified targets never become alias targets in all failure tests.
- **SC-004**: Successful runs atomically swap the alias and retain old-generation metadata through the rollback deadline.
- **SC-005**: Status and CLI outputs contain phase/progress but no document bodies or raw dependency details.

## Assumptions

- Feature 003's Mongo operational collection boundary is available; this feature adds a typed rebuild collection adapter.
- Feature 010 projector wiring supplies the callback that changes its optional target index.
- Feature 011 `INDEX_MAPPING`, `index_name`, and stable alias are authoritative.
