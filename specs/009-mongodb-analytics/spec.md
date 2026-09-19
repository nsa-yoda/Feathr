# Feature Specification: MongoDB Analytics

**Feature Branch**: `009-mongodb-analytics`  
**Created**: 2026-09-18  
**Status**: Accepted for implementation  
**Input**: Feature request in `REQUEST.md`: expose bounded MongoDB date-truncated event statistics.

## Clarifications

- `start` and `end` are optional together. When both are absent, the effective range is the previous 24 hours ending at the current UTC clock; supplying only one is invalid.
- Explicit ranges are inclusive, UTC-aware, and limited to 366 days. The route uses UTC only; clients cannot select another timezone.
- `week` buckets begin on Monday. Points with no events are omitted rather than synthesized as zero rows.
- The aggregation response includes the effective UTC range, requested bucket, fixed timezone, ordered nonzero points, and request ID.

## User Scenarios & Testing

### User Story 1 - Inspect event volume (Priority: P1)

As a reviewer, I need counts grouped by event type and time bucket so I can understand canonical event volume without downloading raw events.

**Independent Test**: Seed known events and verify hour, day, and Monday-based week bucket counts through the Mongo aggregation pipeline.

**Acceptance Scenarios**:

1. **Given** canonical Mongo events, **When** `GET /events/stats?bucket=hour` is requested, **Then** the response contains ordered event-type counts produced by Mongo aggregation.
2. **Given** events crossing hour/day/week boundaries, **When** each bucket is requested, **Then** each event contributes to exactly one UTC bucket and event type.
3. **Given** an empty effective range, **When** statistics are requested, **Then** the response contains an empty points list and the effective range metadata.

### User Story 2 - Bound analytics work (Priority: P1)

As an operator, I need bounded date inputs so a statistics request cannot accidentally scan unbounded history.

**Independent Test**: Exercise omitted, partial, reversed, overlong, naive, and non-UTC ranges and assert safe problem responses.

**Acceptance Scenarios**:

1. **Given** no dates, **When** stats are requested, **Then** the service uses the previous 24-hour UTC range.
2. **Given** an explicit inclusive UTC range no longer than 366 days, **When** stats are requested, **Then** the response echoes the exact effective range.
3. **Given** a partial, reversed, naive, non-UTC, or overlong range, **When** stats are requested, **Then** a safe 422 problem response is returned.

### User Story 3 - Preserve canonical storage semantics (Priority: P2)

As a reviewer, I need analytics to read canonical Mongo state and remain independent from Elasticsearch and Redis projections.

**Independent Test**: Inspect the generated pipeline and dependency failure response; verify no raw event collection or derived-store query is used.

**Acceptance Scenarios**:

1. **Given** an unavailable canonical store, **When** stats are requested, **Then** a safe 503 response with retry guidance is returned.
2. **Given** a valid request, **When** the repository is called, **Then** `$match` precedes `$dateTrunc`/`$group`, stable sorting follows grouping, and raw events are not loaded into Python.

## Edge Cases

- `bucket` accepts only `hour`, `day`, or `week`.
- Date boundaries are inclusive and normalized only when already UTC; non-UTC offsets are rejected.
- Week buckets use Monday as `startOfWeek`.
- A malformed aggregation document is treated as a safe dependency/decode failure.
- Internal Mongo `_id` values and raw driver errors never appear in responses.

## Requirements

### Functional Requirements

- **FR-001**: The service MUST expose `GET /events/stats` with `bucket`, optional `start`, and optional `end` parameters.
- **FR-002**: The service MUST accept only `hour`, `day`, and `week` buckets; week MUST start on Monday.
- **FR-003**: The service MUST use a UTC-aware inclusive range, defaulting to the previous 24 hours when both dates are absent, and reject partial, non-UTC, reversed, or over-366-day ranges.
- **FR-004**: The repository pipeline MUST apply timestamp `$match` before `$dateTrunc` and `$group`, then stable sort by bucket and event type.
- **FR-005**: The pipeline MUST group by event type and truncated time bucket using MongoDB `$dateTrunc`; raw events MUST NOT be aggregated in Python.
- **FR-006**: The response MUST identify the effective start/end, bucket, fixed `UTC` timezone, ordered data points, and request ID.
- **FR-007**: Empty ranges MUST return a successful response with an empty data-point list.
- **FR-008**: Missing, unavailable, or undecodable canonical storage MUST map to safe `application/problem+json` 503 behavior.
- **FR-009**: Tests MUST cover all buckets, boundary timestamps, multiple event types, defaults, invalid ranges, empty results, dependency failure, pipeline order, and a real Mongo aggregation path.
- **FR-010**: The service MUST bound analytics result cardinality to 10,000 grouped points and return a safe 422 response when a valid range would exceed that bound; it MUST NOT silently truncate counts. The canonical aggregation call MUST also use a finite execution deadline so high-cardinality grouping cannot consume an unbounded request lifetime.

### Key Entities

- **AnalyticsRange**: Inclusive UTC start/end with a maximum 366-day span.
- **StatsPoint**: One nonzero count for an event type and UTC bucket.
- **StatsResponse**: Effective range metadata, bucket, timezone, ordered points, and request ID.

## Success Criteria

- **SC-001**: Seeded events crossing hour/day/Monday-week boundaries are counted exactly once in their expected bucket and event type.
- **SC-002**: Every invalid bucket/range case returns a safe 422 response without raw input leakage.
- **SC-003**: Every valid response contains self-describing effective range metadata and points ordered by bucket then event type.
- **SC-004**: The focused Feature 009 suite contains at least 12 behavior-level cases and the existing unit suite remains green.
- **SC-005**: The generated pipeline proves `$match` precedes aggregation and no response contains Mongo `_id`, raw driver details, or derived-store consistency claims.
- **SC-006**: A high-cardinality range is bounded by the pipeline and rejected without returning partial statistics.

## Assumptions

- Feature 003's `MongoEventStore.aggregate()` is the only canonical aggregation boundary.
- Application Mongo client lifecycle and `app.state.event_store` wiring remain owned by later lifecycle work; this route returns 503 when unavailable.
- MongoDB supports `$dateTrunc` with `timezone: "UTC"` and `startOfWeek: "monday"`.
