# Feature 013 Quickstart

1. Install/sync dependencies: `uv sync --dev`.
2. Run focused tests: `.venv/bin/pytest -q tests/unit/test_realtime_stats.py tests/failure/test_realtime_stats_failure.py`.
3. Run the real lifecycle when services are configured: `.venv/bin/pytest -q tests/integration/test_realtime_stats_integration.py` with the integration-test variables `MONGO_URI` and `REDIS_URL` (the application setting is `EVENT_PLATFORM_REDIS_URL`).
4. Request `GET /events/stats/realtime?window_minutes=5` and inspect `X-Cache` and generated/window timestamps.
