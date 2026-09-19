# Feature Specification: Unit Test Coverage Closure

**Feature Branch**: `018-unit-test-coverage`

**Created**: 2026-09-19

**Status**: Accepted

**Input**: Feature request in `specs/018-unit-test-coverage/REQUEST.md`

## User Scenarios & Testing

### User Story 1 - Verify queue and worker semantics (Priority: P1)

As a maintainer, I need deterministic tests for queue state transitions, retry classification, backoff, idempotency, and acknowledgement boundaries so that changes cannot silently lose, duplicate, or prematurely acknowledge events.

**Why this priority**: These are the durable event path and a regression here can lose data or create duplicate records.

**Independent Test**: Run the focused queue, retry, persistence, and idempotency unit selection without external services or real time passing; all boundary and failure cases must pass.

**Acceptance Scenarios**:

1. **Given** a queue with visible, invisible, stopped, or closed messages, **when** send, receive, visibility, delete, redrive, or shutdown operations occur, **then** depth, receipt, admission, and message ownership follow the queue contract.
2. **Given** transient, permanent, unknown, duplicate-equivalent, duplicate-conflict, and exhausted worker outcomes, **when** the worker disposes a delivery, **then** the correct retry, acknowledgement, or dead-letter action occurs with bounded deterministic timing.

### User Story 2 - Verify bounded read-side and control-plane semantics (Priority: P1)

As a maintainer, I need semantic tests for cursors, analytics ranges, search mapping, cache keys and bypass behavior, rate-limit math, and configuration boundaries so that public contracts remain stable as the service evolves.

**Why this priority**: Read-side and control-plane regressions can expose data, bypass protection, or make valid requests fail without being caught by happy-path tests.

**Independent Test**: Run the focused query, analytics, search, cache, rate-limit, and settings selections with deterministic fakes and clocks; each invalid or degraded path must assert its observable result and no unintended dependency work.

**Acceptance Scenarios**:

1. **Given** valid, malformed, tampered, out-of-scope, or boundary cursor and date inputs, **when** the query/search/stat APIs validate them, **then** the safe problem contract is returned or the correct page/pipeline is produced without a downstream call for invalid input.
2. **Given** cache hit, miss, malformed entry, Redis failure, concurrent requests, and configured limits, **when** realtime statistics are requested, **then** the outcome, cache headers, canonical computation, TTL, and single-flight behavior are deterministic.
3. **Given** direct peers, trusted proxy chains, malformed forwarding headers, token exhaustion, refill, route classes, and bounded eviction, **when** rate-limit decisions are made, **then** identity and retry metadata follow the configured policy.

### User Story 3 - Produce an honest coverage signal (Priority: P2)

As a reviewer, I need a reproducible coverage command and a short explanation of what it proves so that measured coverage informs review without becoming a fabricated quality claim.

**Why this priority**: Reviewers need a repeatable signal, while semantic assertions remain the acceptance authority.

**Independent Test**: Run the documented coverage target in the repository environment and verify it produces a report from the unit suite without requiring external services; the README explains that coverage is a signal and does not prove integration or behavioral completeness.

**Acceptance Scenarios**:

1. **Given** a clean checkout with locked dependencies, **when** the coverage command runs, **then** it executes the unit suite and writes a reproducible terminal and/or file report using the same source and test roots as the unit gate.
2. **Given** the measured report, **when** a reviewer reads the README note, **then** the note distinguishes line/branch measurement from semantic, integration, failure, browser, and live-service evidence and does not claim an unmeasured threshold.

## Edge Cases

- A fake clock advances exactly to a retry or visibility deadline; no real sleep is required.
- A queue is full while admission is stopped or closed; the sender wakes and receives the correct classified error.
- A duplicate event has the same identity and payload hash versus the same identity with a conflicting payload; only the equivalent case is acknowledged as an idempotent success.
- A signed cursor has valid encoding but the wrong scope, extra fields, wrong type, or non-canonical value; it is rejected before dependency access.
- A cache entry has valid JSON but the wrong schema version, cardinality, temporal relationship, or totals; it is discarded safely and canonical state is used.
- A proxy header contains empty, non-IP, duplicate, whitespace, or extra-hop values; the direct peer remains the identity unless the complete trusted chain is valid.
- Coverage tooling is unavailable or a service-gated test is selected; the documented command reports that limitation rather than inventing a percentage.

## Requirements

### Functional Requirements

- **FR-001**: The unit suite MUST cover queue admission, visibility, receipts, deletion, redrive, closure, stats, and deterministic boundary timing without real sleeps.
- **FR-002**: The unit suite MUST cover retry classification, jitter/backoff bounds, retry exhaustion, acknowledgement ownership, duplicate equivalence/conflict, and dead-letter disposition.
- **FR-003**: The unit suite MUST cover canonical query cursors, search cursors, analytics ranges/pipelines, malformed and tampered inputs, and zero downstream calls for invalid inputs.
- **FR-004**: The unit suite MUST cover search mapping and fixed query construction, including metadata flattening, deterministic text, unsafe response shapes, and dependency failure translation.
- **FR-005**: The unit suite MUST cover realtime cache keys, schema/temporal/cardinality validation, hit/miss/bypass behavior, Redis failure, TTL propagation, and single-flight coalescing.
- **FR-006**: The unit suite MUST cover token-bucket math, route isolation, direct-peer and trusted-proxy identity, malformed forwarding headers, retry metadata, and local eviction.
- **FR-007**: The unit suite MUST cover settings and problem mapping boundaries, including startup-safe validation, response headers, and redaction behavior.
- **FR-008**: Tests MUST assert observable behavior and state transitions rather than only mock invocation counts; clocks, jitter, and dependency ports MUST remain deterministic.
- **FR-009**: The repository MUST provide a locked-dependency coverage report command that measures the unit suite and documents its evidence limits.
- **FR-010**: Documentation and traceability MUST identify the focused selections, full unit count, coverage command, and what remains service-gated or outside unit evidence.

### Key Entities

- **Semantic Test Case**: A deterministic input, state setup, action, and observable assertion for one contract boundary.
- **Coverage Report**: A reproducibly generated measurement of executed source lines/branches for the unit suite, accompanied by evidence limits.
- **Deterministic Clock**: An injectable time source advanced by a test without wall-clock sleeping.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every mandatory focus area in FR-001 through FR-007 has at least one passing boundary or failure test and is listed in the traceability documentation.
- **SC-002**: The focused Feature 018 selection passes without MongoDB, Elasticsearch, Redis, network access, or wall-clock sleeps.
- **SC-003**: Invalid query, cursor, metadata, cache, proxy, and configuration cases demonstrate their safe result and no unintended downstream operation where applicable.
- **SC-004**: The documented coverage command completes against the locked unit suite and emits a measured report or a clear environment/tooling failure; no unmeasured percentage is asserted in documentation.
- **SC-005**: The full unit suite remains green after the new tests are added, with existing dependency warnings recorded accurately.

## Assumptions

- The existing pytest unit marker and `tests/unit/` directory remain the authoritative isolated suite.
- Real MongoDB, Elasticsearch, Redis, Compose, Postman, and browser behavior remain owned by later integration/runtime/UI features.
- Coverage tooling may be introduced as a development-only locked dependency; no minimum percentage is imposed by this feature.
- Existing production behavior is the contract unless a test exposes a contradiction with an accepted earlier feature; implementation changes remain narrowly scoped to correcting such contradictions.
- README and traceability updates are part of this feature; broader CI orchestration remains Feature 024.
