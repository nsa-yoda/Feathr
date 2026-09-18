# Feature Request: Failure Injection and Recovery Tests

## Required proof

- Mongo unavailable: persistence retries; readiness unhealthy; queue eventually backpressures; no false ack.
- worker post-insert/pre-ack failure: redelivery does not duplicate canonical record.
- ES unavailable: Mongo ingestion/query still works; search returns 503; checkpoint does not skip; recovery catches up.
- Redis unavailable: realtime endpoint bypasses cache; rate limiter falls back locally; system remains usable.
- queue saturation: deterministic 503.
- retry exhaustion: DLQ receives message exactly once relative to source disposition.
- stale/invalid Change Stream checkpoint: system reports recovery/rebuild requirement rather than silently starting at latest.
- rebuild failure: alias never moves to bad target.

## Test hooks

Use explicit dependency seams/fault-injection hooks that are test-only or controlled, not random production behavior. Avoid fragile OS-level chaos if a deterministic failure can prove the same invariant.


## Dependencies

007, 010, 013, 014, 015, 016

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
