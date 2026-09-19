# Integration Harness Contract

## Environment

- `MONGO_URI`: MongoDB replica-set connection string for Mongo, worker, analytics, query, and change-stream scenarios.
- `ELASTICSEARCH_URL`: Elasticsearch endpoint for projection, search, and rebuild scenarios.
- `REDIS_URL`: Redis endpoint for realtime cache and rate-limit scenarios.

A test that lacks a required endpoint skips with the variable name. A configured but unreachable service skips with a safe service-unavailable reason. Credentials and raw event metadata never appear in diagnostics.

## Polling

`poll_until(operation, check, timeout_seconds, interval_seconds, observe)` repeatedly evaluates an async check until it returns a non-`None` result. `timeout_seconds` and `interval_seconds` must be finite and bounded. An optional `observe` callback supplies a small sanitized status summary for failed attempts. The helper raises a diagnostic timeout containing the namespace-qualified operation, attempts, and last safe observation. It uses a monotonic deadline; fixed long sleeps are prohibited.

## Cleanup

Every namespace owner provides an async cleanup path that is called from `finally`, including client closure, Mongo database/collection deletion, Elasticsearch alias/index deletion, and Redis prefix cleanup.
