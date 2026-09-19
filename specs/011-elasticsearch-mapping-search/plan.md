# Feature 011 Implementation Plan: Elasticsearch Mapping and Search API

## Summary

Add a versioned fixed Elasticsearch mapping, deterministic metadata text projection, a typed search service using the Feature 010 async client boundary, and a bounded FastAPI search route with signed filter-bound cursors.

## Technical Context

- Python 3.12+, FastAPI, Pydantic v2, official async Elasticsearch client.
- Existing canonical `CanonicalEvent` and request-ID/problem-handler boundaries are reused.
- The route depends on `request.app.state.search_service`; lifecycle creation remains a later feature.
- Tests use deterministic fakes and explicitly skip real-service integration when URLs are unavailable.

## Constitution Check

- Domain/API contracts remain separate from Elasticsearch driver details.
- Network clients stay behind typed boundaries and raw dependency errors are classified.
- No synchronous network I/O or arbitrary user DSL is introduced.
- Tests and documentation are part of the feature.

## Design

1. `search/mapping.py` owns mapping constants, metadata extraction, and canonical search-document projection.
2. `search/search.py` owns typed query validation, cursor signing, fixed ES request construction, response decoding, and safe dependency translation.
3. `api/routes/search.py` owns HTTP validation, request IDs, and problem responses.
4. `main.py` includes the route; service injection remains explicit for lifecycle compatibility.
