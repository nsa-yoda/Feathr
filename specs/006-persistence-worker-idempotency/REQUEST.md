# Feature Request: Persistence Worker and Idempotency

## Intent

Consume local queue messages and make Mongo persistence correct under redelivery/crash-equivalent scenarios.

## Ack boundary

Delete/ack the queue message only after Mongo confirms persistence or after an existing document with the same `event_id` is verified to have the same canonical payload hash.

## Duplicate outcomes

- no existing event: insert -> success -> ack;
- duplicate event ID + same payload hash: treat as idempotent replay -> ack, increment duplicate metric;
- duplicate event ID + different payload hash: permanent conflict -> never overwrite canonical event; log/metric and route message to DLQ disposition through Feature 007.

## Optional HTTP idempotency key

Use a hashed form only. The worker-level guarantee must not depend on Redis. Repeated keyed requests should map to the same logical event identity where feasible; clarify and test any pre-enqueue conflict-detection limitations caused by the local volatile queue.

## Concurrency

Worker concurrency must be bounded/configurable. Multiple workers may receive different messages, and duplicate delivery must remain safe.

## Crash scenarios to design/test

- crash before insert;
- crash after insert before ack;
- timeout with unknown insert outcome followed by redelivery.

## Tests

Idempotent duplicate, conflicting duplicate, bounded concurrency, ack-after-persist ordering using fakes/spies plus real Mongo integration.


## Dependencies

003, 004, 005

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
