# Feature 018 Quickstart

1. Run the focused deterministic selection:

   ```bash
   .venv/bin/pytest -q tests/unit/test_in_process_queue.py tests/unit/test_retry_backoff_dlq.py tests/unit/test_persistence_worker.py tests/unit/test_event_query_api.py tests/unit/test_mongodb_analytics.py tests/unit/test_search.py tests/unit/test_search_mapping.py tests/unit/test_search_projection.py tests/unit/test_realtime_stats.py tests/unit/test_rate_limit.py tests/unit/test_settings.py tests/unit/test_problems.py
   ```

2. Run `make coverage` to execute all unit tests and write `coverage/coverage.xml` plus the terminal report.
3. Run the repository gates: `make format-check`, `make lint`, `make typecheck`, `make test-unit`, `make test-integration`, `make test-failure`, and `git diff --check`.
4. Read the README coverage note before using the measured percentage; integration, failure, browser, Compose, and live-service evidence remain separate.
