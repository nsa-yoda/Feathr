# Implementation Plan: Retry, Backoff, and Simulated DLQ

**Branch**: `007-retry-backoff-dlq` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Extend the Feature 006 persistence worker and Feature 004 queue with explicit failure classification, visibility-based exponential retry, targeted volatile DLQ disposition, safe diagnostics, and queue-age statistics. Keep retry delays outside worker capacity and preserve the ack-after-persistence invariant.

## Technical Context

**Language/Version**: Python 3.13 runtime in the repository virtual environment; Python 3.12+ contract  
**Primary Dependencies**: asyncio, Pydantic v2, PyMongo Async boundary, pytest/pytest-asyncio  
**Storage**: volatile in-process queue/DLQ; canonical Mongo remains Feature 003  
**Testing**: pytest with deterministic injected clocks and jitter  
**Target Platform**: Linux-compatible async service  
**Project Type**: FastAPI async web service worker package  
**Performance Goals**: retries must not occupy a worker slot while waiting for visibility  
**Constraints**: bounded retry, bounded jitter, no raw exception/metadata diagnostic leakage, no false ack  
**Scale/Scope**: one local queue and bounded worker concurrency in the demo process  

## Constitution Check

- Queue semantics remain at-least-once and volatile; no exactly-once claim is introduced.
- Acknowledgement remains after canonical persistence or equivalent replay verification.
- Transient, permanent, and unknown failures have explicit dispositions; no infinite retry.
- DLQ transition is observable through counters and safe diagnostics, with durable operational metrics deferred to Feature 015.
- Async code changes visibility rather than sleeping on the event loop.

## Project Structure

```text
src/event_platform/queue/in_process.py       # targeted DLQ and oldest-age stats
src/event_platform/queue/__init__.py         # queue exports
src/event_platform/worker/persistence.py     # policy, classification, retry/DLQ disposition
src/event_platform/worker/__init__.py        # worker exports
tests/unit/test_in_process_queue.py           # queue regression coverage
tests/unit/test_retry_backoff_dlq.py          # focused worker failure behavior
docs/architecture/queue-semantics.md         # retry/DLQ documentation
docs/architecture/failure-model.md            # classifications and guarantees
```

**Structure Decision**: Keep queue and persistence worker modules small and explicit. No new service or infrastructure package is required.

## Complexity Tracking

No constitution violations.

