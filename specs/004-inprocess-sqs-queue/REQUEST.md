# Feature Request: In-Process SQS-Style Queue

## Intent

Model queue semantics, not merely asynchronous execution.

## Required interface

A queue port that can later be implemented by SQS without changing route/worker business logic. It should expose the conceptual equivalents of send, receive(long poll), delete by receipt handle, change visibility/retry scheduling, queue stats, and redrive/DLQ inspection required internally.

## Message state

Track stable message ID, immutable body/envelope, enqueue time, current visibility deadline, receive count, current receipt handle/delivery attempt, and diagnostic metadata. Receipt handles must change on redelivery so stale handles cannot delete a newer delivery.

## Semantics

- bounded capacity;
- configurable send timeout;
- long-poll receive;
- visibility timeout;
- message becomes invisible while in flight;
- no delete => visible again after timeout;
- at-least-once while process lives;
- explicit delete only with current valid receipt handle;
- queue close stops new sends/receives predictably;
- metrics/stats are safe under concurrency.

## Critical implementation quality

Use `asyncio` synchronization/condition primitives deliberately. Do not busy-loop. Make time injectable or otherwise test visibility/backoff without slow sleeps.

## Tests

Send/receive/delete; stale receipt rejection; visibility expiry redelivery; long poll wakeup; capacity/send timeout; concurrent consumers; close semantics.


## Dependencies

001, 002

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
