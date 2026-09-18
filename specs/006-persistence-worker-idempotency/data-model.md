# Feature 006 Data Model

- `WorkerMetrics`: immutable counts for inserted, idempotent duplicates, conflicts, decode failures, and processing errors.
- `PersistenceWorker`: queue consumer, Mongo store, bounded concurrency, and optional conflict disposition hook.
