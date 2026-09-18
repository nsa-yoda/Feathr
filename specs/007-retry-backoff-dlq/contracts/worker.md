# Worker Failure Disposition Contract

## RetryPolicy

`RetryPolicy.delay_for(attempt)` returns a bounded non-negative visibility delay. Attempt values start at 1. Jitter is injected as a function of the calculated spread for deterministic tests.

## PersistenceWorker

- `process_once()` returns `True` only for insert, equivalent duplicate, or explicitly accepted conflict disposition.
- Transient failures below the receive limit call `change_visibility` and return `False`.
- Permanent failures and failures at the receive limit call the targeted DLQ operation and return `False`.
- Failed DLQ operations do not delete the source delivery.
- `metrics` includes `retries` and `dlq` counters in addition to Feature 006 counters.
- Each scheduled retry emits one structured `worker.retry_scheduled` record with message ID, optional canonical event ID, attempt, classification, safe reason code, and calculated delay. DLQ transitions emit `worker.dlq` with the same bounded diagnostic fields.
