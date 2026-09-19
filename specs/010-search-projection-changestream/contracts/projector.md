# Change-Stream Projector Contract

## Projector port

- `run()` consumes inserts until cancellation or a terminal reconciliation state.
- `project_change(change)` writes the stable alias and optional rebuild target, then persists the token.
- `status()` returns a safe `ProjectionStatus` snapshot.
- `stop()` stops new consumption while retaining the last checkpoint.

## State guarantees

- Checkpoint persistence follows every required ES write.
- Any required-write failure leaves the previous checkpoint unchanged.
- Invalid resume history transitions to `reconciliation_required` and does not open a new stream from `now`.
- Retry state exposes only bounded safe failure codes.
