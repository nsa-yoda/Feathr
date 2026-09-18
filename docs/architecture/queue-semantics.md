# Queue Semantics — Minute Decisions

## Send

A send either commits a complete immutable message into local queue ownership or fails. Partial enqueue does not exist. Sending is bounded by capacity and an enqueue timeout.

## Receive

Receive may long-poll up to a configured wait. Returned messages immediately gain a new receipt handle and visibility deadline. Only the current receipt handle can delete/change visibility for that delivery.

## Visibility expiry

If the worker does not delete before the visibility deadline, the message becomes eligible for redelivery and receive count increments on its next receipt. The queue implementation should not create duplicate in-memory copies merely to model redelivery; it should transition message state.

## Retry

Worker classifies failure, calculates backoff+jitter, and changes the message's visibility deadline. It must release worker execution capacity rather than sleeping for the backoff duration.

## DLQ

When policy determines no more receives are allowed, create one DLQ entry containing original envelope plus safe diagnostics, then remove source message. If DLQ insertion itself can fail in-memory, disposition logic must avoid silently deleting the source.

## Shutdown

Queue stops new sends/receives once closing begins. In-flight worker tasks receive the normal grace period. Remaining visible/inflight counts are logged before process exit. Since memory disappears, this is diagnostic rather than durable drain.

## SQS compatibility note

The port should avoid exposing Python-specific primitives. Conceptual receipt handle and visibility operations must map naturally to AWS SQS Standard.
