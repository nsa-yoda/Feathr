# Tasks: Elasticsearch Mapping and Search API

## Phase 1: Setup
- [X] T001 Create Feature 011 Spec Kit artifacts and record accepted decisions in `specs/011-elasticsearch-mapping-search/`.

## Phase 2: Foundational
- [X] T002 [P] Define versioned fixed mapping and deterministic metadata text projection in `src/event_platform/search/mapping.py`.
- [X] T003 [P] Define typed search query/page/cursor models and safe error classification in `src/event_platform/search/search.py`.

## Phase 3: User Story 1 - safe mapping
- [X] T004 [US1] Implement search document projection preserving flattened metadata and deterministic metadata text in `src/event_platform/search/mapping.py`.
- [X] T005 [P] [US1] Add mapping and metadata extraction tests in `tests/unit/test_search_mapping.py`.

## Phase 4: User Story 2 - metadata search
- [X] T006 [US2] Implement fixed Elasticsearch search request and response decoding in `src/event_platform/search/search.py`.
- [X] T007 [US2] Add `GET /events/search` route and OpenAPI problem responses in `src/event_platform/api/routes/search.py` and `src/event_platform/main.py`.
- [X] T008 [P] [US2] Add search behavior and dependency failure tests in `tests/unit/test_search.py` and `tests/failure/test_search_failures.py`.

## Phase 5: User Story 3 - deterministic pagination
- [X] T009 [US3] Implement signed filter-bound search-after cursor and bounded query validation in `src/event_platform/search/search.py`.
- [X] T010 [P] [US3] Add pagination, tamper, unsafe DSL, and bounds tests in `tests/unit/test_search.py`.
- [X] T011 [US3] Add real Elasticsearch integration coverage with explicit service skip in `tests/integration/test_search_live.py`.

## Phase 6: Polish and quality gates
- [X] T012 Update architecture, traceability, AI workflow, and quickstart documentation with Feature 011 evidence.
- [X] T013 Run analyze, converge, staff/comprehensive review, remediation, and final quality gates; record the report under `specs/011-elasticsearch-mapping-search/reviews/`.

## Dependencies

T001 precedes T002-T003. T002-T003 precede T004-T011. US1 precedes US2; US2 precedes US3. T012-T013 follow implementation.

## MVP

User Story 1 plus the fixed search request from User Story 2 provide a safe searchable projection; pagination is required before feature acceptance.
