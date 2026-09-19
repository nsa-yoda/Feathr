# Implementation Plan: Unit Test Coverage Closure

**Branch**: `018-unit-test-coverage` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

## Summary

Close semantic unit-test gaps across the durable event path and read/control boundaries, then add a reproducible coverage report command and honest evidence documentation. The implementation is primarily test and developer-tooling work; production behavior changes only if a test demonstrates a contradiction with an accepted contract.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: pytest, pytest-asyncio, coverage.py, existing FastAPI/Pydantic/MongoDB/Elasticsearch/Redis adapters

**Storage**: Fakes and in-memory state for unit tests; no new persistent storage.

**Testing**: pytest unit suite, deterministic fake ports/manual clocks, coverage.py terminal/XML report, Ruff, strict mypy.

**Target Platform**: Linux/macOS developer environments using the locked uv environment.

**Project Type**: Async Python web service.

**Performance Goals**: Focused tests complete without wall-clock sleeps or external services; coverage command uses the existing unit scope.

**Constraints**: No fabricated coverage threshold, no production service dependency in unit tests, no tests that only assert mock invocation.

**Scale/Scope**: Existing `src/event_platform` and `tests/unit` boundaries; approximately ten mandatory focus areas from the request.

## Constitution Check

- **II. Domain/API boundaries**: PASS — tests exercise public ports and typed contracts.
- **VI. Async correctness**: PASS — async tests use pytest-asyncio and injectable clocks, not blocking sleeps.
- **VII. Observability**: PASS — failure and redaction assertions verify safe evidence.
- **VIII. Testing**: PASS — semantic behavior is the acceptance authority; coverage is supplemental.
- **IX. Spec-first discipline**: PASS — plan follows the accepted Feature 018 spec and focuses only on named gaps.

## Project Structure

```text
tests/unit/
├── test_in_process_queue.py
├── test_retry_backoff_dlq.py
├── test_persistence_worker.py
├── test_event_query_api.py
├── test_mongodb_analytics.py
├── test_search.py
├── test_search_mapping.py
├── test_realtime_stats.py
├── test_rate_limit.py
├── test_settings.py
└── test_problems.py
Makefile
README.md
docs/requirements-traceability.md
docs/ai-workflow-log.md
pyproject.toml
uv.lock
coverage/                 # generated and ignored report output
```

**Structure Decision**: Extend existing unit modules and add only shared developer-tooling/documentation changes. Generated coverage output is ignored and never committed.

## Implementation Phases

1. Measure the baseline and identify uncovered semantic branches.
2. Add deterministic tests for durable queue/worker/retry/idempotency behavior.
3. Add deterministic tests for query/search/analytics/cache/rate-limit/settings/problem boundaries.
4. Add the locked coverage dependency/target and README/traceability evidence notes.
5. Run convergence, staff review, comprehensive review, and all repository gates.

## Complexity Tracking

No constitution violations. Coverage tooling is a small development-only addition required by the accepted deliverable; no production abstraction is introduced.
