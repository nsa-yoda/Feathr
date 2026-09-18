# Feature 007 Quickstart

Run focused behavior tests:

```bash
.venv/bin/pytest -q tests/unit/test_retry_backoff_dlq.py tests/unit/test_in_process_queue.py
```

Run all local quality gates:

```bash
.venv/bin/pytest -q tests/unit
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy
```

The queue and DLQ are process-local. A restart discards queued and dead-lettered messages; production evolution is AWS SQS redrive as described in `docs/operations/sqs-migration.md`.

