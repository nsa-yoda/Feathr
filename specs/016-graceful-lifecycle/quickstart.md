# Feature 016 Quickstart

1. Configure optional dependency URLs and `EVENT_PLATFORM_SHUTDOWN_GRACE_PERIOD`.
2. Start the service and inspect `/health/components` for lifecycle and worker state.
3. Send events, then terminate the process; confirm admission stops, queue depth
   is logged, tasks drain or cancel at the deadline, and clients close in order.
4. Run `.venv/bin/pytest -q tests/unit/test_lifecycle.py tests/unit/test_app_lifecycle.py`.
