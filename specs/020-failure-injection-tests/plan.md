# Implementation Plan: Failure Injection and Recovery Tests

**Branch**: `020-failure-injection-tests` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

## Summary

Expand the deterministic failure suite around existing typed dependency ports so each requested outage, retry, fallback, checkpoint, queue, and rebuild invariant is directly asserted. Keep changes test-first and add only a production correction if a failing acceptance test proves the invariant is absent.

## Technical Context

**Language/Version**: Python 3.12+
**Dependencies**: Existing pytest, pytest-asyncio, FastAPI TestClient, Pydantic, queue/worker/search/cache/rate-limit ports
**Test execution**: `pytest -q tests/failure -m failure`; no external endpoints required
**Constraints**: injected clocks and failures, bounded retries, safe diagnostics, no OS-level chaos, no wall-clock sleeps, no raw dependency details

## Constitution Check

- **I. Canonical truth**: PASS — Mongo failure tests preserve source deliveries and canonical insert semantics.
- **III. Async correctness**: PASS — tests use async seams and immediate awaitable sleeps; no blocking network I/O.
- **VI. Failure semantics**: PASS — transient/permanent/unknown dispositions, readiness, retries, DLQ, recovery, and reconciliation are explicit.
- **VII. Observability**: PASS — assertions inspect safe state/reason codes rather than raw exceptions or payloads.
- **VIII. Testing**: PASS — every requested failure mode receives deterministic behavioral assertions.
- **IX. Spec-first discipline**: PASS — accepted artifacts and traceability precede implementation.

## Project Structure

```text
 tests/failure/test_failure_injection_recovery.py
 tests/failure/test_search_projection_failure.py
 tests/failure/test_search_rebuild_failure.py
 tests/failure/test_rate_limit_failure.py
 tests/failure/test_realtime_stats_failure.py
 tests/failure/test_lifecycle_failure.py
 docs/testing-strategy.md
 docs/requirements-traceability.md
 docs/ai-workflow-log.md
```

## Implementation Phases

1. Add deterministic Mongo/queue/worker/readiness and queue-saturation acceptance tests.
2. Add post-insert/pre-ack redelivery and exact DLQ disposition tests.
3. Add ES outage/recovery/checkpoint and invalid-resume reconciliation tests.
4. Add Redis cache/rate-limit fallback and rebuild alias safety assertions where the existing files do not already cover the full requirement.
5. Reconcile documentation, run analyze/implement/converge, complete staff and specialized reviews, run repository gates, and commit the approved slice.

## Complexity Tracking

No new production abstraction is planned. Test doubles are local to the failure suite and implement existing protocol shapes; they deliberately expose only the state needed to assert recovery invariants.
