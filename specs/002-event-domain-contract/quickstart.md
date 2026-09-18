# Feature 002 Quickstart

Feature 002 is pure domain validation and requires no external services.

```bash
.venv/bin/pytest -q tests/unit/test_event_domain.py
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy
```

The tests cover valid input, timestamp and URL boundaries, recursive metadata limits, Unicode, deterministic payload hashing, idempotency-key hashing, and safe validation failures. MongoDB, Elasticsearch, Redis, HTTP routing, and queue behavior are deferred to dependent features.
