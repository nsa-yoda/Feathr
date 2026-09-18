# Feature 006 Quickstart

Construct `PersistenceWorker(queue, store, concurrency=4)`, call `await process_once()` in deterministic tests, or `await run(stop_event)` in a lifespan-owned task. Inject a conflict disposition callback when Feature 007 is available.
