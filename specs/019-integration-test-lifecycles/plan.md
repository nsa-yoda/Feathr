# Implementation Plan: Integration Test Lifecycles

**Branch**: `019-integration-test-lifecycles` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

## Summary

Add a shared real-service integration harness, app-level lifecycle tests for ingestion/query/search/cache, bounded poll diagnostics, unique namespace cleanup, and the minimal missing Elasticsearch search-service wiring required for the configured search route.

## Technical Context

**Language/Version**: Python 3.12+
**Dependencies**: Existing async PyMongo, Elasticsearch, Redis, FastAPI, pytest, pytest-asyncio
**Integration inputs**: `MONGO_URI`, `ELASTICSEARCH_URL`, `REDIS_URL`
**Test execution**: pytest integration marker; service-gated skips when endpoints are absent/unreachable
**Constraints**: real dependencies only; no mocks for lifecycle assertions; bounded monotonic polling; no fixed long synchronization sleep; safe diagnostics; cleanup in `finally`

## Constitution Check

- **I. Canonical truth**: PASS — MongoDB remains the source of event assertions.
- **III. Async correctness**: PASS — async clients are owned by lifespan or test cleanup and polling never blocks the loop.
- **VI. Failure semantics**: PASS — missing/unreachable services are explicit skips and poll timeouts are diagnostic.
- **VII. Observability**: PASS — app lifecycle wiring exposes the configured search service and retains structured health state.
- **VIII. Testing**: PASS — scenarios use real MongoDB, Elasticsearch, and Redis boundaries.
- **IX. Spec-first discipline**: PASS — artifacts and traceability precede implementation.

## Project Structure

```text
tests/integration/support.py
 tests/integration/test_integration_lifecycles.py
 tests/integration/test_search_projection_integration.py
 src/event_platform/main.py
 tests/integration/README.md
 README.md
 docs/testing-strategy.md
 docs/requirements-traceability.md
 docs/ai-workflow-log.md
```

## Implementation Phases

1. Add the harness contract and namespace/poll helpers.
2. Wire `ElasticsearchSearchService` into app lifespan and clean it up on shutdown.
3. Add real app/service lifecycle tests for all six requested scenarios, reusing existing lower-level tests where they already prove a boundary.
4. Document environment variables, skip semantics, cleanup, and exact scenario coverage.
5. Run analyze, implement, converge, reviews, and repository gates.

## Complexity Tracking

No new production abstraction is planned beyond assigning the existing typed search service at the configured app boundary. The integration helper is test-only and intentionally small.
