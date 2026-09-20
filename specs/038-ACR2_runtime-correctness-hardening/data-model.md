# Data Model: ACR2 Runtime Correctness and Production Readiness

## Idempotency record

```text
scope + key (unique _id)
fingerprint
event_id
status: reserved | enqueued | completed | released
reservation_token
generation (monotonic)
created_at / lease_expires_at
enqueued_at / completed_at
```

Only the reservation owner token and observed generation may transition a record. A stale owner cannot complete, release, or overwrite a newer generation.

## Projector lease and checkpoint

```text
projector_id (unique _id)
owner_id
fencing_generation (monotonic)
lease_expires_at / renewed_at

checkpoint_id (unique _id)
source_position
owner_id
fencing_generation
updated_at
```

Checkpoint updates require the current owner and generation and reject lower source positions.

## Storage manifest additions

- `event_idempotency`: canonical producer coordination metadata with bounded retention/index policy.
- `search_projection_leases`: derived projector ownership metadata.
- `search_projection_checkpoints`: derived source progress, rebuildable from Mongo events.
