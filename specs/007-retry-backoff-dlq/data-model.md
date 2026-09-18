# Data Model: Retry, Backoff, and Simulated DLQ

## RetryPolicy

- `base_delay`: positive seconds used for attempt 1
- `max_delay`: positive cap
- `jitter_ratio`: bounded fraction applied around the exponential delay
- `max_receive_count`: positive number of receives, with default 5

## DeadLetter

- `delivery`: immutable original message ID, body, receipt, receive count, and enqueue time
- `classification`: `transient`, `permanent`, or `unknown`
- `reason_code`: bounded stable code such as `mongo_dependency`, `invalid_envelope`, `event_conflict`, or `unknown_failure`
- `attempts`: receive count at disposition

## QueueStats

- capacity, total depth, visible count, in-flight count, DLQ depth
- oldest queued age in seconds, calculated from the injected queue clock

