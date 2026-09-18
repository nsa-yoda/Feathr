---
description: "Canonical async MongoDB persistence, query primitives, and required indexes"
---

# Feature Specification: MongoDB Store and Indexes

**Feature Branch**: `003-mongodb-store-indexes`  
**Created**: 2026-09-18  
**Status**: Ready for review

## Clarifications

- The canonical event collection is `events`; event IDs are stored as lowercase UUID strings so the same representation works across API, Mongo, and later projections.
- Query results and time-oriented compound indexes follow the authoritative descending `(timestamp,event_id)` architecture contract; equality filter fields remain ascending prefixes.
- Repository pagination uses an exclusive `(timestamp, event_id)` continuation pair. Cursor encoding belongs to the API feature; this repository accepts typed values only.
- Index bootstrap is an explicit idempotent operation. Feature 004 may call it from application lifespan after a client is configured; this feature does not make Mongo mandatory for foundation startup.
- Query and aggregation methods translate PyMongo failures into typed internal errors and never expose a raw collection to routes.
- Repository query values enforce bounded filter lengths and a maximum 366-day date range; Feature 008 owns opaque cursor encoding and public endpoint defaults.

## User Scenarios & Testing

### User Story 1 - Persist and resolve canonical events (Priority: P1)

As a worker, I can insert a canonical event and fetch it by immutable ID when duplicate delivery must be resolved.

**Independent Test**: Against a real replica-set MongoDB, insert an event, fetch it, and verify duplicate event IDs produce the typed duplicate error.

### User Story 2 - Query with stable filtering and ordering (Priority: P1)

As a query service, I can apply supported filters and a typed continuation pair while receiving deterministic `(timestamp,event_id)` ordering.

**Independent Test**: Seed events with ties and different filters in real MongoDB and verify ordered pages and filter composition.

### User Story 3 - Bootstrap justified indexes (Priority: P1)

As an operator, I can run index bootstrap repeatedly and inspect deterministic names and definitions.

**Independent Test**: Run bootstrap twice against real MongoDB, list indexes, and assert the five required definitions exist without metadata or wildcard indexes.

### User Story 4 - Run bounded aggregation primitives (Priority: P1)

As an analytics service, I can submit an application-owned aggregation pipeline through the repository without receiving raw collection access.

**Independent Test**: Execute a typed pipeline against real MongoDB and verify dependency failures become internal errors.

## Functional Requirements

- **FR-001**: The store MUST use PyMongo's async API and MUST keep Mongo client/collection access behind `event_platform.storage`.
- **FR-002**: Insert MUST serialize a `CanonicalEvent`, preserve producer fields and server fields, and translate duplicate event IDs to `EventAlreadyExists` without leaking the driver exception.
- **FR-003**: Fetch-by-ID MUST use the unique event ID and return a typed canonical event or `None`.
- **FR-004**: Filtered queries MUST support event type, user ID, source URL, inclusive timestamp bounds, an exclusive `(timestamp,event_id)` continuation, bounded page size, and deterministic descending `(timestamp,event_id)` ordering.
- **FR-005**: Aggregation MUST accept only a repository pipeline value, return materialized mappings, and translate PyMongo failures to `MongoDependencyError`.
- **FR-006**: Index bootstrap MUST be idempotent and create exactly the justified indexes: unique event ID; timestamp+event ID; type+time+ID; user+time+ID; source URL+time+ID.
- **FR-007**: Index names and key order MUST be deterministic and documented; arbitrary metadata and wildcard indexes MUST NOT be created.
- **FR-008**: Repository methods MUST catch and classify PyMongo dependency errors and MUST NOT expose raw driver exceptions or collection handles to API callers.

## Edge Cases

- Duplicate event insertion is a typed conflict even if all other fields match.
- Missing IDs return `None`; missing query filters return all events subject to the page limit.
- A continuation pair is exclusive, so an event equal to the cursor is not repeated.
- Page limits outside 1–1000 are rejected before any network call.
- Empty aggregation stages are allowed; non-mapping stages are rejected before any network call.
- Index bootstrap may be called concurrently or repeatedly and must converge on the same names/keys.

## Success Criteria

- **SC-001**: Real Mongo integration proves insert/fetch/duplicate behavior and no raw driver error crosses the repository boundary.
- **SC-002**: Real Mongo integration proves stable filtered ordering and exclusive continuation behavior.
- **SC-003**: Real Mongo integration proves all five required indexes and deterministic definitions after two bootstrap calls.
- **SC-004**: Unit tests cover BSON mapping, page validation, pipeline validation, and exception translation without a live service.
- **SC-005**: No route or application service imports a Mongo collection or PyMongo exception directly.
