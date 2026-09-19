# Feature Specification: Realtime Statistics Cache

**Feature Branch**: `013-realtime-stats-cache`
**Created**: 2026-09-19
**Status**: Accepted for implementation
**Input**: `specs/013-realtime-stats-cache/REQUEST.md`

## User Scenarios & Testing

### User Story 1 - View a rolling realtime summary (Priority: P1)

A reviewer requests the realtime statistics endpoint and receives a bounded summary for the default five-minute UTC window, including total events, counts by event type, generated time, and window boundaries.

**Why this priority**: The endpoint is the feature's primary reviewer and dashboard value.

**Independent Test**: Seed canonical events with timestamps inside and outside the window, request the endpoint, and verify only in-window events are counted and the response is deterministic.

**Acceptance Scenarios**:

1. **Given** canonical events across and outside a five-minute window, **When** the endpoint is requested without parameters, **Then** it returns total and per-type counts only for the inclusive rolling window.
2. **Given** a supported explicit window length, **When** the endpoint is requested with that length, **Then** the response reports matching UTC window bounds and does not collide with another window's result.
3. **Given** an invalid or out-of-range window length, **When** the endpoint is requested, **Then** it returns the standard safe 422 problem response.

### User Story 2 - Reuse fresh cached results (Priority: P1)

A reviewer repeats the same request and receives a cache hit while the configured short TTL remains valid.

**Why this priority**: Cache reuse is the core latency and Redis demonstration requirement.

**Independent Test**: Use a deterministic cache and clock, request once, request again with the same parameters, and verify Mongo is consulted once and the second response has `X-Cache: HIT`.

**Acceptance Scenarios**:

1. **Given** no cache entry, **When** the request succeeds against Mongo, **Then** it returns `X-Cache: MISS` and stores a deterministic response with the configured TTL.
2. **Given** a valid cached entry, **When** the same parameterized request is made, **Then** it returns the cached response with `X-Cache: HIT`.
3. **Given** an expired or malformed cached entry, **When** the request is made, **Then** it recomputes from Mongo and returns `X-Cache: MISS`.

### User Story 3 - Continue during Redis failure (Priority: P1)

A reviewer can still obtain current canonical statistics when Redis is unavailable, and the response makes the degraded cache path visible.

**Why this priority**: Redis is derived state and must not become an availability dependency.

**Independent Test**: Inject a cache that raises dependency errors, verify Mongo is queried, and assert a successful response with `X-Cache: BYPASS` and a structured degraded log event.

**Acceptance Scenarios**:

1. **Given** Redis read or write failure and healthy Mongo, **When** the endpoint is requested, **Then** it computes from Mongo, returns 200, and sets `X-Cache: BYPASS`.
2. **Given** Mongo failure regardless of Redis state, **When** the endpoint is requested, **Then** it returns the standard safe retryable 503 problem response.
3. **Given** concurrent cache misses for one key, **When** requests arrive together, **Then** request coalescing limits the canonical computation to one in-flight computation per service instance.

## Edge Cases

- The rolling window is inclusive at both UTC boundaries and uses a server-generated end time.
- Window length is an integer number of minutes from 1 through 60; the default is 5.
- Empty windows return zero total and an empty type-count object.
- Unknown event types remain separate bounded string keys; no arbitrary metadata is returned.
- Cache payloads with invalid JSON, wrong schema, or negative counts are discarded and recomputed.
- Redis timeout, connection, serialization, and TTL-write failures are degraded cache paths, not endpoint failures.
- Mongo aggregation and decode failures are safe 503 responses with no raw dependency details.

## Requirements

### Functional Requirements

- **FR-001**: The service MUST expose `GET /events/stats/realtime` with a default five-minute rolling UTC window.
- **FR-002**: The service MUST accept only bounded integer window lengths from 1 through 60 minutes and reject invalid values with the standard problem contract.
- **FR-003**: The response MUST include total event count, counts grouped by event type, `generated_at`, `window_start`, `window_end`, and `request_id`.
- **FR-004**: The canonical computation MUST read MongoDB event state using an inclusive timestamp range and a bounded aggregation result.
- **FR-005**: The cache MUST use a versioned key containing every result-affecting parameter and deterministic JSON encoding.
- **FR-006**: Successful cache lookup MUST return `X-Cache: HIT`; a fresh computation and successful cache population MUST return `MISS`; a Redis dependency failure MUST return `BYPASS`.
- **FR-007**: Cache entries MUST use a configurable TTL defaulting to 10 seconds and MUST never be treated as canonical state.
- **FR-008**: Redis read, write, timeout, and decode failures MUST be classified and logged as degraded cache behavior while Mongo success still returns 200.
- **FR-009**: Mongo dependency or result-decoding failures MUST return a safe retryable 503 problem response.
- **FR-010**: The service MUST coalesce concurrent misses for the same cache key within one process without unbounded locks or tasks.
- **FR-011**: Cache responses MUST not expose raw event metadata, credentials, Redis keys, or dependency exception text.
- **FR-012**: Unit, failure-path, and real Mongo/Redis integration tests MUST cover miss/hit, TTL expiry, parameterized keys, Redis bypass, Mongo errors, and coalescing.

### Key Entities

- **RealtimeStatsQuery**: Bounded window length and effective UTC interval used for cache identity and canonical aggregation.
- **RealtimeStatsResponse**: Deterministic derived summary with counts, timestamps, cache-independent request identity, and schema version.
- **CacheEntry**: Versioned serialized response with short expiration; disposable and reconstructable from Mongo.

## Success Criteria

- **SC-001**: Repeated identical requests within the default TTL perform one canonical aggregation and return one `MISS` followed by `HIT` responses.
- **SC-002**: Requests using different valid window lengths never return one another's cached response.
- **SC-003**: With Redis unavailable but Mongo healthy, the endpoint returns a correct 200 response with `X-Cache: BYPASS` for every request.
- **SC-004**: With Mongo unavailable, the endpoint returns the repository problem contract with status 503 and `Retry-After` without leaking dependency details.
- **SC-005**: The focused feature tests cover all acceptance scenarios and complete without arbitrary sleeps.

## Assumptions

- MongoDB remains the canonical source and Feature 009 aggregation boundaries are reused.
- Redis is reachable through an optional configured URL; absence of configuration is equivalent to a degraded cache path.
- The endpoint is unauthenticated and inherits the repository's later rate-limit middleware.
- A short process-local single-flight lock is sufficient for the single-process demo; distributed locking is out of scope.
- Realtime freshness is bounded by the cache TTL and is communicated by the generated timestamp.
