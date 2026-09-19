# Feature Specification: ACR1 Request Idempotency

**Feature**: `030-ACR1_request-idempotency`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1_B P1-05, P2-03

## User Scenarios & Testing

### User Story 1 - Retry an ingestion safely (Priority: P1)

As an API client, I can retry an uncertain ingestion with the same `Idempotency-Key` and receive the original result without creating another canonical event.

**Independent Test**: Submit identical requests concurrently and after a process restart, then verify one canonical event and equivalent responses.

**Acceptance Scenarios**:

1. **Given** a completed keyed request, **When** the same client repeats the same payload and key, **Then** the API returns the original status and event identity.
2. **Given** concurrent identical keyed requests, **When** they race, **Then** exactly one request creates the event and all successful callers converge on its result.
3. **Given** a keyed request, **When** the same key is reused with a different payload, **Then** the API returns a deterministic conflict problem.
4. **Given** equal payloads with different keys, **When** both are submitted, **Then** they remain distinct requests.

### User Story 2 - Operate the idempotency registry (Priority: P2)

As an operator, I can observe contention and conflicts without exposing raw keys or internal hashes.

**Acceptance Scenarios**:

1. **Given** an in-flight keyed request, **When** a duplicate arrives, **Then** it receives a bounded, documented disposition rather than creating another event.
2. **Given** expired records, **When** retention cleanup runs, **Then** it removes only records outside the documented replay window.

## Edge Cases

- A process stops after reserving a key but before storing the outcome.
- A retry arrives while the original request is still running.
- Key scope changes when tenant or authenticated client identity is introduced.
- A stored historical outcome uses an older registry version.

## Functional Requirements

- **FR-001**: The API MUST implement `Idempotency-Key` as a durable request registry, not as global payload deduplication.
- **FR-002**: Registry identity MUST include the caller scope, key, operation, and a canonical request fingerprint.
- **FR-003**: Reservation and completion MUST be atomic under concurrent requests and across application replicas.
- **FR-004**: A matching completed retry MUST replay the original externally observable outcome and canonical event identity.
- **FR-005**: Reusing a key with a different request fingerprint MUST return a stable conflict problem.
- **FR-006**: The registry MUST define recovery semantics for abandoned in-flight reservations.
- **FR-007**: Registry records MUST survive application restart for the configured replay window.
- **FR-008**: Raw keys, request fingerprints, and internal hashes MUST NOT appear in API responses or default logs.
- **FR-009**: Retention and record-version rules MUST be documented and testable.
- **FR-010**: Metrics MUST distinguish new reservations, safe replays, in-flight contention, conflicts, and recovery.

## Key Entities

- **Idempotency Record**: Scoped key, request fingerprint, state, outcome reference, timestamps, and schema version.
- **Request Fingerprint**: Canonical representation used only to determine whether a retry matches the reserved request.
- **Recorded Outcome**: The stable API result replayed for a matching completed request.

## Success Criteria

- **SC-001**: A 100-request concurrent retry test creates exactly one canonical event.
- **SC-002**: Matching retries remain safe across process restart and multiple application replicas.
- **SC-003**: Mismatched key reuse returns the documented conflict response in every tested race order.
- **SC-004**: Contract tests confirm no raw idempotency key or internal fingerprint is exposed.

## Assumptions and Scope

- Authentication and tenant identity are added by the production security feature; the registry is designed to accept that caller scope.
- This feature governs HTTP request replay. Canonical event duplicate rules remain a separate domain concern.
