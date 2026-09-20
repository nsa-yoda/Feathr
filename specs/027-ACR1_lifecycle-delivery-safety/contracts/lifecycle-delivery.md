# Lifecycle and Delivery Contract

- Shutdown calls `stop_accepting()` before waiting for workers.
- A task that remains alive after cancellation timeout prevents shared resource closure and emits `lifecycle.resources_isolated`.
- A worker renews an active receipt at a bounded fraction of the configured visibility timeout.
- Stale delete, visibility, and dead-letter operations emit `worker.ownership_lost` and return a safe incomplete outcome.
