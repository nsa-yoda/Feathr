# Feature 014 Quickstart

1. Set `EVENT_PLATFORM_REDIS_URL=redis://localhost:6379/0` and optional bounded route policy settings.
2. Start the API and send repeated requests to `/events`, `/query`, `/search`, and `/health/live` from one client.
3. Confirm limited routes return `RateLimit-*` headers, then a `429` with `Retry-After`; confirm health remains available.
4. Stop Redis and repeat. Confirm responses use the conservative local limiter and structured degraded events are emitted.
5. Run `.venv/bin/pytest -q tests/unit/test_rate_limit.py tests/failure/test_rate_limit_failure.py tests/integration/test_rate_limit_integration.py`.
