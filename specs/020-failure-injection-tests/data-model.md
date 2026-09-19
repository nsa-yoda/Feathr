# Feature 020 Data Model

## FaultInjection

- `operation`: bounded dependency operation label
- `failures_remaining`: deterministic number of failures before recovery
- `error_code`: allowlisted safe code exposed to the test
- `calls`: count of attempted operations

## DeliveryDisposition

- `message_id`: stable queue identity
- `attempts`: receive count
- `outcome`: `retry`, `acknowledged`, or `dead_lettered`
- `canonical_count`: number of persisted records for the event
- `dlq_count`: number of DLQ entries for the source disposition

## ProjectionEvidence

- `checkpoint_before`: last durable resume token before injected outage
- `writer_calls`: attempted derived writes
- `checkpoint_after`: token saved only after successful write
- `state`: running, retrying, degraded, or reconciliation_required
- `failure_code`: safe operational code

## RebuildEvidence

- `old_index`: serving generation before the run
- `target_index`: candidate generation
- `alias_after`: serving generation after failure
- `phase`: durable failed/completed phase
- `cleanup_calls`: failed target cleanup attempts
