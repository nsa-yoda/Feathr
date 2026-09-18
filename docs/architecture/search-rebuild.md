# Search Projection and Online Rebuild Details

## Stable alias rule

Application search code and ordinary live projector writes use the stable alias. Business code must not know the current physical generation name.

## Dual-write rule during rebuild

The projector's normal successful operation becomes:

1. write event ID/document to stable alias;
2. if a rebuild target is active and differs from the alias-resolved physical index, write the same document ID to that target;
3. only after all required writes succeed, persist the Change Stream checkpoint.

This ensures an event arriving while the bulk scan is underway appears in both the currently served generation and the candidate generation.

## Bulk rebuild scan

Use deterministic `_id`/event iteration and bounded bulk batches. Bulk operations must inspect per-item errors rather than treating HTTP 200 as universal success. Retry only retryable items.

## Verification

At minimum require:

- no unresolved permanent bulk/index failures;
- target document count converges to canonical event count for append-only events;
- projector checkpoint/lag indicates live dual writes are caught up;
- mapping/settings fingerprint matches desired version;
- sample/known-event checks pass where practical.

Count equality alone is not sufficient if failed documents could be replaced by unexpected extras, so track indexed event IDs/errors and use at least sampled consistency verification.

## Alias swap

Use one atomic aliases request removing old target and adding new target. If it fails, leave rebuild state failed/retriable and continue serving old alias. Never manually point application config at the target.

## Cleanup

Retain prior generation for a configurable period. Cleanup must refuse to delete the index currently targeted by the alias or an active rebuild target.
