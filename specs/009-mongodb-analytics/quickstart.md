# Feature 009 Quickstart

Run focused analytics tests:

```bash
.venv/bin/pytest -q tests/unit/test_mongodb_analytics.py
```

Run the real Mongo boundary test when `MONGO_URI` points to a MongoDB replica set:

```bash
.venv/bin/pytest -q tests/integration/test_mongodb_analytics_integration.py
```

Example request:

```text
GET /events/stats?bucket=day&start=2026-01-01T00:00:00Z&end=2026-01-02T00:00:00Z
```
