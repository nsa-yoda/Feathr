# Feature 008 Quickstart

Run focused query tests:

```bash
.venv/bin/pytest -q tests/unit/test_event_query_api.py
```

The route requires `app.state.event_store` to be provided by the application lifecycle. Until the later lifecycle feature wires a real Mongo client, an absent store returns a safe 503. Query results read canonical Mongo state and may precede Elasticsearch projection.
