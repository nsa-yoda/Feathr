# Feature Specification: Postman Reviewer Suite

**Feature**: 022-postman-reviewer-suite  
**Status**: Accepted for implementation  
**Source**: [REQUEST.md](REQUEST.md)

## User Scenarios & Testing

### User Story 1 - Verify the public API contract (Priority: P1)

A reviewer imports one collection and local environment, runs the folders in order, and sees assertions for health, ingestion, validation, query, analytics, search, cache, rate limiting, and dependency-visible behavior.

**Acceptance Scenarios**

1. Given the API is reachable, when the reviewer runs the environment and health folders, then liveness, readiness, component status, and metrics responses have asserted status and key fields.
2. Given a normal stack, when the reviewer runs ingestion and deduplication, then a `202` response captures an event ID, request ID, and idempotency key for later requests.
3. Given an asynchronously persisted event, when query/search folders run, then bounded polling finds the captured event or exits with a clear assertion failure before the deadline.

### User Story 2 - Demonstrate bounded failures and controls (Priority: P1)

A reviewer can run negative requests and observe problem responses, validation failures, rate-limit metadata, and safe degraded dependency responses without inspecting implementation details.

**Acceptance Scenarios**

1. Invalid event and query requests assert a 4xx status and problem fields including `status`, `detail`, `error_code`, and `request_id`.
2. The rate-limit request asserts successful queued service behavior or full-backlog `429` with a positive `Retry-After` header, and the collection includes a repeatable overflow path for environments configured with a small admission backlog.
3. Search dependency-visible behavior accepts a healthy `200` result or a safe `503` problem response without treating either as an unbounded hang.

### User Story 3 - Run the end-to-end demo (Priority: P2)

A reviewer can run the numbered demo folder from an empty or normal local stack and inspect captured variables and response assertions without manually editing request bodies.

**Acceptance Scenarios**

1. Folder order is explicit from environment verification through end-to-end demo, and every request includes a test script with status/schema/key assertions.
2. The local environment contains only non-secret defaults and a configurable base URL, poll deadline, and rate-limit burst count.
3. Newman-compatible CLI instructions identify prerequisites, import/run commands, and the expected live-service limitation when no stack is available.

## Functional Requirements

- **FR-001**: The collection MUST be valid Postman Collection v2.1 JSON and use the twelve numbered folders requested by the feature.
- **FR-002**: Every request MUST assert its expected status and key response fields or problem schema fields.
- **FR-003**: Ingestion MUST assert `202`, capture `event_id`, `request_id`, `user_id`, and an idempotency key, and expose those variables to later folders.
- **FR-004**: Query and search requests MUST use bounded polling with a configurable deadline and MUST match the captured event ID.
- **FR-005**: The suite MUST cover validation 4xx responses, cursor handling, analytics stats, Elasticsearch search, realtime cache outcomes, health, metrics, and rate-limit behavior.
- **FR-006**: Dependency-visible requests MUST accept only documented healthy or safe degraded statuses and assert problem fields for degraded responses.
- **FR-007**: The demo folder MUST run sequentially from the captured event and show canonical query, search, realtime stats, and metrics evidence.
- **FR-008**: The environment MUST contain no credentials, use a configurable `baseUrl`, and document a bounded polling deadline and rate-limit burst setting.
- **FR-009**: A Newman-compatible runner path and import/run instructions MUST be provided; missing Newman or unavailable services MUST fail clearly rather than silently pass.
- **FR-010**: Docker-free regression tests MUST validate collection structure, folder order, assertion presence, variable capture, and absence of fixed sleep commands.

## Edge Cases

- The event is accepted but persistence or search indexing is delayed; polling continues until the deadline.
- The event already exists from a previous run; a unique idempotency key and user suffix prevent false matches.
- Search or Redis is unavailable; safe `503` or cache bypass/degraded assertions remain visible.
- A rate-limit configuration permits all requests; the rate-limit assertion still validates the `429` contract when encountered and does not claim a 429 that did not occur.
- Newman is not installed or the API is unreachable; the CLI exits nonzero with an actionable message.

## Success Criteria

- **SC-001**: Collection and environment parse as JSON and pass the Docker-free contract tests.
- **SC-002**: The collection has all twelve numbered folders, at least one request in each, and every request contains status/key assertions.
- **SC-003**: A normal stack run captures one event ID and reuses it in canonical query, search, stats/cache, and demo requests with bounded polling no longer than the configured deadline.
- **SC-004**: The collection includes explicit assertions for `202`, 4xx problem responses, `429`/`Retry-After`, health, metrics, and safe `503` dependency behavior.
- **SC-005**: Newman-compatible execution returns nonzero when the base URL is unavailable or the collection/environment is invalid.

## Assumptions and Scope

- Authentication is not part of the current API contract; the environment contains no auth secrets.
- Postman is a reviewer acceptance surface, not a replacement for unit, failure, integration, or Compose smoke tests.
- Feature 023 owns the full UI; this feature covers API demonstration only.
