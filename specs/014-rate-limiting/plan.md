# Implementation Plan: Mandatory Rate Limiting

**Branch**: `014-rate-limiting` | **Date**: 2026-09-18 | **Spec**: [spec.md](spec.md)

## Summary

Add a typed rate-limit domain with route policies, atomic Redis Lua token bucket, conservative bounded local fallback, safe peer/proxy identity extraction, and HTTP middleware/problem/header integration. Keep Redis optional and close its client in application lifespan.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI/Starlette, Pydantic Settings, redis.asyncio
**Storage**: Redis derived coordination; process-local bounded fallback
**Testing**: pytest, pytest-asyncio, Ruff, mypy; service-gated Redis integration
**Target Platform**: Linux ASGI service
**Project Type**: Web service
**Performance Goals**: One atomic Redis execution per limited request; no blocking event-loop I/O; bounded local memory.
**Constraints**: Redis outage must not fail open; identity headers are untrusted by default; route keys cannot contain arbitrary URLs.
**Scale/Scope**: Four route classes and a bounded local entry cap, with policies configured centrally.

## Constitution Check

- Domain/API contracts stay separate from Redis and middleware adapters: PASS.
- Async network clients are created/closed in lifespan: PASS; rate limiter receives an app-owned client.
- No broad exception swallowing: PASS; Redis failures are classified and trigger local fallback.
- Typed boundaries, injectable clocks, and tests for every feature: PASS.
- No secrets, raw keys, request bodies, or dependency errors in logs: PASS.

## Project Structure

```text
src/event_platform/rate_limit/
├── __init__.py
├── models.py          # route classes, policy, decision, token math
├── identity.py        # peer/proxy normalization
├── redis_bucket.py    # atomic Lua adapter and Redis failure boundary
└── local_bucket.py    # monotonic bounded fallback
src/event_platform/api/middleware/rate_limit.py
src/event_platform/core/settings.py
src/event_platform/main.py
tests/unit/test_rate_limit.py
tests/failure/test_rate_limit_failure.py
tests/integration/test_rate_limit_integration.py
```

**Structure Decision**: Extend the existing single ASGI project with an isolated `rate_limit` domain and one middleware adapter. Existing problem and lifecycle modules remain the integration seams.

## Complexity Tracking

No constitution violations.
