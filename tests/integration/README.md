# Integration tests

These tests exercise real service boundaries. Set the endpoint variables required by the selected module:

- `MONGO_URI`: MongoDB replica-set endpoint for canonical persistence, queries, analytics, workers, and change streams.
- `ELASTICSEARCH_URL`: Elasticsearch endpoint for projection, search, and rebuild lifecycles.
- `REDIS_URL`: Redis endpoint for cache and rate-limit lifecycles.

Run the suite with:

```bash
make test-integration
```

Feature 019 adds `tests/integration/support.py`, which allocates unique namespaces and provides bounded monotonic polling with safe timeout diagnostics. Tests clean their Mongo databases, Elasticsearch aliases/indices, checkpoints, and Redis keys in `finally` blocks. Missing or unreachable service endpoints produce explicit service-gated skips; skipped tests are not evidence of a passing lifecycle. The six requested lifecycles are covered across the app-level ingestion/query/search/cache tests and the existing real-service analytics, duplicate/redelivery, and rebuild modules.
