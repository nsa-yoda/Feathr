---
description: "Validated event input and immutable canonical event contract"
---

# Feature Specification: Event Domain Contract

**Feature Branch**: `002-event-domain-contract`

**Created**: 2026-09-18

**Status**: Ready for review

**Input**: User description: "Define the event contract precisely before ingestion/storage code exists, including bounded metadata, normalization, server fields, and deterministic hashing."

## Clarifications

No interactive clarification questions were required. The request and locked architecture provide the needed semantic defaults; the concrete bounds and normalization rules below are explicit acceptance decisions.

## User Scenarios & Testing

### User Story 1 - Validate producer event input (Priority: P1)

As an event producer, I can submit a valid event payload and receive a typed, normalized domain value that is safe for later ingestion and storage.

**Why this priority**: Every ingestion, persistence, query, projection, and analytics feature depends on one unambiguous event contract.

**Independent Test**: Construct the domain input model with valid and invalid payloads and assert accepted values, normalized UTC timestamps, URL rules, and bounded metadata behavior without external services.

**Acceptance Scenarios**:

1. **Given** a non-empty event type, bounded user ID, timezone-aware timestamp, HTTP(S) URL, and valid JSON metadata, **When** the payload is validated, **Then** it is accepted and the timestamp is represented in UTC.
2. **Given** a naive timestamp, unsupported URL scheme, empty required string, or client-supplied server field, **When** the payload is validated, **Then** validation fails with a safe field-level error and no payload is logged.

### User Story 2 - Enforce metadata abuse limits (Priority: P1)

As a platform operator, I can rely on explicit metadata limits so one event cannot consume unbounded memory, serialization, or downstream mapping capacity.

**Why this priority**: Metadata is flexible and untrusted; rejecting abusive shape and size is required before any queue or database accepts it.

**Independent Test**: Exercise exact boundary and over-limit metadata for serialized bytes, nesting, keys, key lengths, strings, numbers, lists, and non-finite values.

**Acceptance Scenarios**:

1. **Given** metadata within every declared limit, **When** it is validated, **Then** it is accepted without changing its JSON meaning.
2. **Given** metadata over any declared limit or containing a non-JSON value, **When** it is validated, **Then** validation fails with a 422-ready domain error that identifies the violated category without echoing the complete metadata.

### User Story 3 - Create an immutable canonical event (Priority: P1)

As a persistence worker, I can turn validated producer input into a server-owned canonical event with stable identity and payload hashing.

**Why this priority**: Mongo uniqueness, idempotent replay, queue envelopes, and future projections all depend on server fields being separated from producer input.

**Independent Test**: Build canonical events with injected IDs and clocks, compare hashes for semantically equivalent payloads, and verify server fields are excluded from the payload hash.

**Acceptance Scenarios**:

1. **Given** validated input, an event ID, and an ingestion clock, **When** a canonical event is created, **Then** it contains UUID identity, UTC ingestion time, schema version 1, the normalized producer fields, and a SHA-256 payload hash.
2. **Given** producer payloads with different JSON key order but the same values, **When** they are canonicalized, **Then** their payload hashes match; changing a value changes the hash.
3. **Given** an optional idempotency key, **When** a canonical event is created, **Then** only its SHA-256 hash is retained and the raw key is never part of the canonical event.

## Edge Cases

- Producer timestamps may be up to five minutes in the future relative to the injected/current UTC clock; older historical events have no lower age limit.
- A timestamp exactly at the future-skew boundary is accepted; a timestamp beyond it is rejected.
- Offset-aware timestamps are normalized to UTC while preserving the instant.
- Metadata depth counts the root object as level 1; maximum depth is five. Total object keys across the tree are limited to 64, and each key is 1–64 characters.
- Metadata serialized with deterministic compact JSON must be at most 16 KiB; strings are at most 512 characters, finite numbers have absolute value at most 10^18, and each list is at most 128 items.
- JSON supports objects, arrays, strings, finite numbers, booleans, and null. NaN and infinity are rejected.
- Client attempts to provide `event_id`, `ingested_at`, `schema_version`, `payload_hash`, or `idempotency_key_hash` are rejected as extra fields.
- Validation errors must not log full metadata, credentials, or arbitrary request bodies.

## Requirements

### Functional Requirements

- **FR-001**: The domain MUST validate `event_type` as a non-empty string of at most 128 characters without restricting the vocabulary to an enum.
- **FR-002**: The domain MUST validate `user_id` as a non-empty string of at most 256 characters.
- **FR-003**: The domain MUST accept only timezone-aware ISO 8601 timestamps, normalize them to UTC, and reject timestamps more than five minutes ahead of the current UTC clock.
- **FR-004**: The domain MUST accept only HTTP and HTTPS source URLs of at most 2,048 characters and preserve their semantic URL meaning without destructive rewriting.
- **FR-005**: The domain MUST accept JSON metadata only when it is an object within the declared byte, depth, key, key-length, string, number, and list limits; object keys must be 1–64 characters and finite numbers must have absolute value at most 10^18.
- **FR-006**: The domain MUST reject client-owned payloads containing server-owned fields or non-JSON values.
- **FR-007**: Canonical event creation MUST assign an immutable UUID `event_id`, UTC `ingested_at`, schema version 1, and a lowercase hexadecimal SHA-256 `payload_hash`.
- **FR-008**: Payload hashing MUST use compact UTF-8 JSON with recursively sorted object keys, no insignificant whitespace, and no server-owned fields.
- **FR-009**: When supplied, an idempotency key MUST be stored only as a SHA-256 hash; its raw value MUST NOT be retained or logged.
- **FR-010**: Domain validation failures MUST expose safe categories suitable for an HTTP 422 problem response without echoing full metadata or secret values.
- **FR-011**: The domain MUST reject control characters in event types and user IDs, and MUST reject tuples or other non-JSON containers instead of coercing them into JSON values.

### Key Entities

- **EventInput**: Client-controlled event type, producer timestamp, user ID, normalized HTTP(S) source URL, and bounded JSON metadata.
- **CanonicalEvent**: Immutable server-owned event envelope containing the validated input plus `event_id`, `ingested_at`, `schema_version`, `payload_hash`, and optional `idempotency_key_hash`.
- **Canonical payload**: Deterministic JSON representation of only the five producer-controlled semantic fields used for hashing.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of valid boundary cases in the domain test suite normalize timestamps and URLs according to this contract.
- **SC-002**: Every declared metadata limit has passing boundary and failing over-limit tests, including Unicode and non-finite number cases.
- **SC-003**: Equivalent producer payloads produce identical payload hashes across at least 100 repeated constructions, independent of object key insertion order.
- **SC-004**: No domain validation test output contains full metadata, an idempotency key, or another sentinel secret value.
- **SC-005**: The Feature 002 unit suite passes without MongoDB, Elasticsearch, Redis, network access, or application startup.

## Assumptions

- Feature 001 supplies Pydantic v2, strict mypy, Ruff, pytest, and the `src/event_platform/domain/` ownership boundary.
- The domain layer is pure application code; HTTP routes, queue envelopes, Mongo serialization, and external clients belong to dependent features.
- A UUID is suitable for the immutable event identity; ordering and pagination are owned by later query features and will not rely on UUID lexical order.
- URL canonicalization performed by the typed URL validator may normalize harmless syntax such as a missing path slash, but it must not resolve redirects, fetch network resources, or rewrite path/query semantics.
- Historical event age is unrestricted; operational retention and query date-range limits are later feature concerns.
