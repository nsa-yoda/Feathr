# Feature Specification: Elasticsearch Mapping and Search API

**Feature Branch**: `011-elasticsearch-mapping-search`
**Created**: 2026-09-18
**Status**: Accepted for implementation
**Input**: `REQUEST.md`

## Clarifications

- The index mapping is versioned by physical generation while callers use the stable `events-search` alias.
- Metadata text extraction is deterministic, depth-first, and includes scalar leaf keys and values; nulls contribute no text, arrays preserve item order, and original metadata remains in `flattened`.
- Search accepts a bounded free-text query plus stable exact type/user/date filters. Clients cannot submit arbitrary Elasticsearch JSON or field names.
- Results use descending timestamp and event ID sort with a signed, filter-bound continuation cursor.
- A missing or unavailable search dependency returns a safe 503 problem response; the API never falls back to Mongo query semantics.

## User Scenarios & Testing

### User Story 1 - Create a safe versioned mapping (Priority: P1)

As an operator, I need a stable mapping so arbitrary metadata keys cannot create unbounded index fields.

**Independent Test**: Assert the mapping has `dynamic: false`, explicit canonical fields, `metadata` as `flattened`, and `metadata_text` with standard/lowercase/asciifolding analysis.

### User Story 2 - Search metadata (Priority: P1)

As a user, I need to search metadata terms with case and diacritic-insensitive matching while preserving canonical event identity.

**Independent Test**: Submit bounded queries to a fake Elasticsearch service and verify the generated safe query, extracted text, hit decoding, exact filters, and safe 503 dependency behavior.

### User Story 3 - Page deterministically (Priority: P1)

As a user, I need stable continuation pages without accepting raw Elasticsearch DSL.

**Independent Test**: Verify signed filter-bound cursors, timestamp/event ID sort, page bounds, tamper rejection, and no arbitrary query fields.

## Edge Cases

- Empty or control-character queries, oversized queries, invalid date ranges, malformed cursors, and oversized page sizes are rejected with safe 422 responses.
- Metadata nested objects, arrays, booleans, numbers, strings, and nulls produce deterministic text without dynamic mapping fields.
- Malformed or dependency-failure search responses return safe 503 behavior without raw driver details.

## Requirements

- **FR-001**: The service MUST publish a versioned Elasticsearch mapping with top-level `dynamic: false`, explicit canonical keyword/date fields, `metadata` as `flattened`, and analyzed `metadata_text`.
- **FR-002**: Metadata text MUST be deterministic, depth-first, preserve array order, include scalar leaf keys and values, and omit nulls.
- **FR-003**: The service MUST expose `GET /events/search` with a bounded free-text query and optional exact event type, user, and UTC date filters.
- **FR-004**: Clients MUST NOT submit arbitrary Elasticsearch JSON DSL, field names, scripts, or sort expressions.
- **FR-005**: Results MUST be sorted by timestamp descending then event ID descending and use a signed filter-bound `search_after` cursor.
- **FR-006**: Query and page bounds MUST be validated before dependency access and invalid inputs MUST return safe problem responses.
- **FR-007**: Elasticsearch dependency failures or malformed responses MUST return a safe 503 problem response with retry guidance; Mongo search fallback is forbidden.
- **FR-008**: Tests MUST cover mapping, metadata extraction, case/diacritic behavior, nested metadata, pagination, unsafe query rejection, and dependency failures.

## Key Entities

- **SearchDocument**: canonical fields, bounded flattened metadata, and deterministic `metadata_text`.
- **SearchQuery**: bounded free text, exact filters, UTC range, page size, and opaque cursor.
- **SearchPage**: projected event items, page size, continuation cursor, and request ID.

## Success Criteria

- **SC-001**: Mapping assertions prove no arbitrary metadata key can create a top-level field.
- **SC-002**: Representative nested metadata searches return matching events regardless of case or accents.
- **SC-003**: 100% of page boundary tests preserve deterministic order without duplicate or skipped hits.
- **SC-004**: Every malformed or dependency-failure case returns a safe problem response and never raw Elasticsearch details.

## Assumptions

- Feature 010 owns the live projection writer and stable alias; Feature 011 owns mapping and read-side search only.
- Elasticsearch lifecycle/client ownership remains in the later application lifecycle feature; the route uses an injected typed service boundary.
- Search responses contain canonical source fields and sort values produced by the configured mapping.
