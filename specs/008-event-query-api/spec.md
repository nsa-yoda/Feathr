# Feature Specification: Event Query API

**Feature Branch**: `008-event-query-api`

**Created**: 2026-09-18

**Status**: Accepted for implementation

**Input**: Feature request in `REQUEST.md`: provide bounded filtered event reads with opaque keyset pagination.

## Clarifications

- The public query uses `start` and `end` inclusive UTC bounds; a range longer than 366 days or with start after end is rejected.
- The default page size is 50 and the maximum is 200.
- Cursors are versioned, signed, URL-safe tokens containing only the last returned UTC timestamp and event ID. A cursor is process-local and expires when the service signing key changes; it never exposes Mongo internals.

## User Scenarios & Testing

### User Story 1 - Browse canonical events (Priority: P1)

As a reviewer, I need to retrieve accepted canonical events with bounded pages so I can inspect the source of truth without loading the whole collection.

**Why this priority**: Querying canonical Mongo data is the primary read path and must remain independent of eventually consistent search projections.

**Independent Test**: Seed a static event set, request the first page, follow the returned cursor, and verify every event appears once in descending timestamp/event ID order.

**Acceptance Scenarios**:

1. **Given** persisted canonical events, **When** a reviewer requests `GET /events`, **Then** the response contains bounded items, page metadata, a request ID, and an optional next cursor.
2. **Given** two events with identical timestamps, **When** pages are traversed with the cursor, **Then** event IDs provide deterministic tie-breaking with no duplicate or missing item.
3. **Given** an unavailable canonical store, **When** the endpoint is requested, **Then** it returns a safe `503 application/problem+json` response.

### User Story 2 - Filter event history (Priority: P1)

As a reviewer, I need exact event type, user, source URL, and time filters so I can narrow canonical history predictably.

**Why this priority**: Filters make the endpoint useful for operational investigation while preserving the storage contract's bounded inputs.

**Independent Test**: Exercise every filter alone and representative combinations against a fake query store, including URL normalization and invalid ranges.

**Acceptance Scenarios**:

1. **Given** a valid event type, user ID, source URL, or UTC range, **When** the query is made, **Then** only matching canonical events are returned.
2. **Given** a source URL without its normalized trailing slash, **When** the query is made, **Then** it matches the canonical normalized URL representation.
3. **Given** an overlong filter, unsupported cursor, start after end, or range over 366 days, **When** the query is made, **Then** a safe 422 problem response is returned.

### User Story 3 - Understand consistency (Priority: P2)

As a reviewer, I need the query response to make clear that it reads canonical Mongo state and can differ temporarily from Elasticsearch search results.

**Why this priority**: Explicit consistency language prevents reviewers from inferring a false cross-store transaction guarantee.

**Independent Test**: Inspect the response contract and API documentation while the projection is behind; query still returns canonical events without claiming search freshness.

**Acceptance Scenarios**:

1. **Given** an event persisted in Mongo but not yet projected to search, **When** `GET /events` is requested, **Then** the event is eligible to appear and the contract does not claim Elasticsearch parity.

## Edge Cases

- An empty result returns an empty items list and no cursor.
- `limit=0`, `limit>200`, malformed base64/signature/version, cursor payload missing fields, and cursor timestamp not UTC are rejected.
- A cursor whose timestamp/event ID is syntactically valid but does not match the active filter is rejected rather than silently changing query scope.
- A source URL is normalized through the same HTTP URL model used by canonical events.
- Internal Mongo `_id` values are never returned.
- Mongo dependency and decode errors are mapped to safe 503 behavior; raw driver details are not returned.

## Requirements

### Functional Requirements

- **FR-001**: The service MUST expose `GET /events` with optional event type, start, end, user ID, source URL, limit, and cursor parameters.
- **FR-002**: The service MUST validate filter lengths, UTC timestamps, start/end ordering, and a maximum 366-day range.
- **FR-003**: The default limit MUST be 50 and the maximum MUST be 200.
- **FR-004**: Results MUST be ordered by timestamp descending and event ID descending, using an exclusive keyset continuation predicate.
- **FR-005**: The cursor MUST be opaque, versioned, URL-safe, tamper-validated, and bounded in size.
- **FR-006**: The cursor MUST encode only the last returned timestamp and event ID plus its version/signature; it MUST NOT expose Mongo `_id` or arbitrary query data.
- **FR-007**: The response MUST include canonical event items, the effective page limit, request ID, and an optional `next_cursor`.
- **FR-008**: The endpoint MUST return safe RFC 9457-style problem responses for invalid input and unavailable canonical storage.
- **FR-009**: The endpoint MUST read canonical Mongo data and MUST NOT claim Elasticsearch search consistency or write to derived stores.
- **FR-010**: Tests MUST cover each filter, combinations, URL normalization, equal-timestamp pagination, malformed/tampered cursors, page limits, empty results, and dependency failure.

### Key Entities

- **EventCursor**: Versioned signed continuation containing a UTC timestamp and event UUID.
- **EventPage**: Canonical event items, effective limit, request ID, and optional continuation token.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every seeded static event appears exactly once across a complete cursor traversal, including equal-timestamp groups.
- **SC-002**: 100% of invalid filter, range, limit, and cursor cases return safe 422 problem responses without raw input leakage.
- **SC-003**: Every valid page contains no more than 200 items and uses a cursor whose signature rejects tampering.
- **SC-004**: The focused Feature 008 test suite contains at least 12 behavior-level cases and the full existing unit suite remains green.
- **SC-005**: No response body contains an internal Mongo `_id`, raw driver exception, or claim that Elasticsearch is transactionally synchronized.

## Assumptions

- Feature 003's typed `MongoEventStore.query()` owns canonical filtering and descending keyset predicates.
- Feature 008 provides route-level cursor encoding/validation; later lifecycle work owns production Mongo client creation and closure.
- A process-local signing key is sufficient for the single-process demo; production deployments should use a configured stable secret.
- Query results can include events not yet visible to Elasticsearch.
