# Feature Specification: ACR1 Cursor and API Boundary Hardening

**Feature**: `031-ACR1_cursor-api-boundary-hardening`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P2-004; AUTO_CODE_REVIEW_1_B P1-01, P2-03, P2-08, P2-12, P3-01, P3-02

## User Scenarios & Testing

### User Story 1 - Use pagination across replicas and key rotation (Priority: P1)

As an API client, I can continue pagination after a restart, on another replica, or during a signing-key rotation.

**Independent Test**: Issue a cursor on one instance and consume it on another using current and previous key versions.

**Acceptance Scenarios**:

1. **Given** two production replicas, **When** one issues a cursor and the other validates it, **Then** pagination succeeds.
2. **Given** an active key rotation, **When** an unexpired cursor signed by the previous key is used, **Then** it remains valid during the overlap window.
3. **Given** a cursor for another endpoint or filter set, **When** it is replayed, **Then** it is rejected with the documented problem response.

### User Story 2 - Receive safe, bounded API data (Priority: P1)

As an API consumer, I receive only public fields and bounded results with consistent time and URL validation.

**Acceptance Scenarios**:

1. **Given** an event record, **When** it is returned by list or detail APIs, **Then** internal payload and idempotency hashes are absent.
2. **Given** a source URL containing user information, **When** it is submitted, **Then** validation rejects it.
3. **Given** equivalent timestamps with different offsets, **When** they are stored and queried, **Then** comparisons use normalized UTC instants.
4. **Given** adjacent analytical windows, **When** results are combined, **Then** boundary events are counted exactly once.

## Edge Cases

- A cursor expires during a key-rotation overlap.
- A configured key set is missing, duplicated, or uses an unknown version.
- A storage adapter returns more rows or buckets than the service limit.
- A source URL contains percent-encoded user information.
- A time range is empty, reversed, or exactly on a bucket boundary.

## Functional Requirements

- **FR-001**: Production cursor signing keys MUST come from shared versioned configuration and MUST NOT be generated independently by each process.
- **FR-002**: Cursor verification MUST support an explicit current key and bounded previous-key overlap for rotation.
- **FR-003**: All cursor endpoints MUST use one versioned codec contract with endpoint, filter, sort, and expiry binding.
- **FR-004**: Startup MUST reject missing or invalid production cursor-key configuration.
- **FR-005**: Public event DTOs MUST exclude persistence-only hashes, retry bookkeeping, and internal control fields.
- **FR-006**: URL validation MUST reject credentials or user information, including encoded forms.
- **FR-007**: Aware timestamps MUST be normalized to UTC before storage, comparison, cursor encoding, and aggregation.
- **FR-008**: Analytical time ranges MUST use documented half-open interval semantics.
- **FR-009**: Result and bucket limits MUST be enforced at the storage boundary as well as the API boundary.
- **FR-010**: Validation errors MUST use the shared problem contract without disclosing signing or storage internals.

## Key Entities

- **Cursor Key Set**: Versioned current and previous verification keys plus rotation metadata.
- **Cursor Envelope**: Version, scope, filters, ordering position, and expiry protected by a signature.
- **Public Event DTO**: Stable client-facing event representation.
- **Time Window**: Normalized half-open interval used for queries and aggregation.

## Success Criteria

- **SC-001**: Cross-instance, restart, and rotation tests complete pagination without invalidating eligible cursors.
- **SC-002**: Schema tests prove internal hashes never appear in public event responses.
- **SC-003**: Boundary tests count each event once across adjacent windows and time-zone offsets.
- **SC-004**: Oversized adapter results are capped before unbounded materialization.

## Assumptions and Scope

- Key distribution uses the deployment secret-management mechanism defined by the production security feature.
- This feature preserves existing endpoint shapes except where removing internal fields is a required security correction.
