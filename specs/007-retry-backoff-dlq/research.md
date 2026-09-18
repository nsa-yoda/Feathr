# Research: Retry, Backoff, and Simulated DLQ

## Decisions

1. Reuse `InProcessQueue` visibility and receipt semantics. A retry changes visibility and releases the worker task immediately.
2. Keep failure classification at the persistence-worker boundary: translated `MongoDependencyError` is transient, validation and immutable-ID conflicts are permanent, and other `Exception` values are unknown with a bounded retry budget.
3. Use an immutable `RetryPolicy` with base delay 1 second, cap 60 seconds, jitter ratio 20%, and maximum receive count 5. Inject a jitter function in tests.
4. Add a targeted queue DLQ operation so one poison message cannot cause unrelated eligible messages to move when a worker exhausts its budget.
5. Keep DLQ entries in memory and expose safe diagnostics separately from the immutable envelope. This preserves the demo's volatile limitation and avoids raw exception leakage.

## Rejected alternatives

- Sleeping inside the worker was rejected because it consumes bounded worker capacity and delays unrelated deliveries.
- Retrying every exception forever was rejected because permanent data errors would create poison loops.
- Putting retry state in Redis or Mongo was rejected because the request explicitly asks for a simulated in-process DLQ and later features own durable operational state.

