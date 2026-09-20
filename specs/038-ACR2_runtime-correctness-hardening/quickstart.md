# ACR2 Verification Quickstart

1. Read `AUTO_CODE_REVIEW_2.md` and `CODEX_WORK.LOG`; confirm the working tree contains only intended changes plus preserved untracked review artifacts.
2. Run focused P0/P1 tests:

   ```bash
   .venv/bin/pytest -q tests/unit/test_lifecycle.py tests/unit/test_ingestion_api.py tests/unit/test_persistence_worker.py tests/unit/test_search_projection.py tests/unit/test_rate_limit.py
   ```

3. Run formatting, lint, typecheck, unit, integration, and failure targets through the repository `Makefile` where dependencies are available.
4. Run backend coverage with branch measurement and the configured threshold.
5. Validate Docker Compose configuration and smoke/Postman gates when Docker and services are available.
6. Append each result, unavailable dependency, and intentional deferral to `CODEX_WORK.LOG` with an ISO timestamp.

The in-process queue is intentionally not crash durable. A production deployment should migrate queue admission and visibility to SQS/Kafka-equivalent infrastructure while retaining the same acknowledgement and idempotency contracts.
