# SQS Migration Design Notes

## Port compatibility

The queue abstraction should map cleanly to SQS Standard operations: `SendMessage`, long-poll `ReceiveMessage`, `DeleteMessage`, and `ChangeMessageVisibility`.

## Runtime changes

With SQS, split API and worker into separate deployments. API can scale horizontally because queue ownership is external. Workers scale from queue depth/age and Mongo capacity.

## Semantics retained

At-least-once delivery and idempotent event persistence remain required. Do not remove unique event IDs/deduplication merely because SQS is durable.

## Production concerns

IAM least privilege, encryption, queue policy, DLQ/redrive configuration, CloudWatch alarms, message size, visibility timeout versus max processing time, retention period, poison-message operations, and optionally FIFO only if ordering/dedup requirements truly justify it.
