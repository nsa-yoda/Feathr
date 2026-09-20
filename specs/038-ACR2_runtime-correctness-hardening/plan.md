# Implementation Plan: ACR2 Runtime Correctness and Production Readiness

**Branch**: `038-ACR2_runtime-correctness-hardening` | **Date**: 2026-09-20 | **Spec**: `spec.md`

## Summary

Remediate verified P0 and P1 correctness defects first, then close the storage, CI, documentation, performance, and hygiene findings that can be addressed without changing the assignment's technology choices. The design keeps MongoDB canonical, keeps the simulated in-process queue, and makes lifecycle, idempotency, and projection ownership semantics explicit and testable.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic, PyMongo Async, MongoDB, Elasticsearch, Redis, pytest, Ruff, mypy

**Storage**: MongoDB canonical events and state; Elasticsearch derived search; Redis derived cache/rate-limit state

**Testing**: pytest unit, integration, failure-mode, concurrency, coverage, Docker smoke and Postman/Newman where available

**Target Platform**: Linux container and local macOS development

**Project Type**: Async web service with in-process worker and operational CLI

**Performance Goals**: Bounded queue memory, bounded delayed-rate-limit backlog, bounded projector batches, no synchronous network I/O in async paths

**Constraints**: Preserve FastAPI/MongoDB/Elasticsearch/Redis/in-process queue assignment contract; accepted 202 is process-volatile and must be documented

## Constitution Check

- MongoDB remains canonical; derived services remain rebuildable and degradable.
- Lifecycle and queue behavior use explicit acknowledgement, visibility, retry, and shutdown boundaries.
- Network clients remain lifespan-managed and async; no broad silent exception handling.
- Tests accompany every corrected state transition and failure path.
- Any production-only evolution not implemented in the assignment is recorded as an intentional deferral.

## Design

1. **Lifecycle and shutdown**: separate admission stop from task stop; mark persistence as drainable, stop admission first, wait for queue depth/in-flight work through a deadline, then force-stop and report residual work. Enforce `TaskPolicy.criticality` for normal return, exception, cancellation, and optional restart behavior.
2. **Producer idempotency**: add owner token and generation to reservation records. Use atomic CAS for stale takeover, owner-fenced completion/release, and explicit state for queue admission. Scope records by stable authenticated client identity with an explicit local single-client fallback.
3. **Projection ownership**: add a Mongo-backed lease with expiry and fencing generation. Require lease ownership for renewal/checkpoint writes, make checkpoints monotonic, and use bounded Elasticsearch bulk writes with acknowledged-prefix retry behavior.
4. **Admission control**: correct route classification, add a bounded process-wide delayed-request gate, and return 429 only when bounded admission is full. Preserve Redis leaky-bucket semantics and local degradation.
5. **Schema and operations**: add idempotency and projector lease/checkpoint collections to storage manifests/index bootstrap, repair CI gates, update CORS/metrics/coverage behavior, remove safe archive artifacts, and align README/ARCHITECTURE/operational documentation with runtime behavior.

## Project Structure

```text
src/event_platform/
├── api/                 # FastAPI routes and middleware
├── core/                # lifecycle, settings, domain contracts
├── queue/               # in-process SQS-style queue
├── storage/             # Mongo canonical stores and manifests
├── search/              # Elasticsearch projection and rebuilds
├── rate_limit/          # Redis/local leaky bucket and route policy
└── main.py              # composition and lifespan wiring
tests/unit/              # deterministic state-machine tests
tests/integration/       # real dependency and multi-process semantics
tests/failure/           # dependency and lifecycle failure tests
docs/                    # operational and AI workflow documentation
```

## Complexity Tracking

| Addition | Reason | Simpler option rejected |
|---|---|---|
| Mongo projector lease/fencing | In-process locks cannot protect multi-replica checkpoints | Process-local lock fails after replica/process boundaries |
| Idempotency owner token/generation | Reservation, queue, and completion are separate operations | Timestamp-only stale takeover races |
| Bounded shutdown phases | Accepted 202 work must drain before workers stop | Setting one global stop event strands queued work |

