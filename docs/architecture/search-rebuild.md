# Search Projection and Online Rebuild Details

## Stable alias rule

Application search code and ordinary live projector writes use the stable alias. Business code must not know the current physical generation name.

## Dual-write rule during rebuild

The projector's normal successful operation becomes:

1. write event ID/document to stable alias;
2. if a rebuild target is active and differs from the alias-resolved physical index, write the same document ID to that target;
3. only after all required writes succeed, persist the Change Stream checkpoint.

This ensures an event arriving while the bulk scan is underway appears in both the currently served generation and the candidate generation.

## Online rebuild protocol

The rebuild captures the maximum Mongo generated ObjectId after candidate
dual-write is active. Backfill scans only documents at or below that durable
boundary. The change-stream projector writes each accepted event to the stable
alias and candidate before saving its resume token and source-position marker.
The reconciling phase waits for the candidate projector marker to reach the
current canonical high-water boundary; events inserted during backfill therefore
remain in the candidate even though they are outside the original scan.

The Mongo rebuild lease increments a fencing token. Rebuild-state writes and
lease renewal include the owner and token, so an expired or superseded owner
cannot regress a newer run. The candidate is identity-reconciled against the
canonical source through the persisted boundary, allowing live extra documents
while rejecting missing or wrong event IDs.

## Bulk rebuild scan

Use deterministic `_id`/event iteration and bounded bulk batches. Bulk operations must inspect per-item errors rather than treating HTTP 200 as universal success. Retry only retryable items.

## Verification

At minimum require:

- no unresolved permanent bulk/index failures;
- target count is not below the canonical scan count and no unresolved failures remain;
- source high-water and projector/candidate checkpoint are persisted and converged;
- every canonical event ID through the boundary exists in the candidate;
- mapping/settings fingerprint matches desired version;
- sample/known-event checks pass where practical.

Count equality alone is not sufficient if failed documents could be replaced by unexpected extras, so the rebuild performs bounded identity reconciliation. Live events beyond the captured boundary are allowed only after the candidate has been dual-written and convergence has been established.

## Alias swap

Use one atomic aliases request removing old target and adding new target. If it fails, leave rebuild state failed/retriable and continue serving old alias. Never manually point application config at the target. After a committed swap, state persistence failure is recorded as `reconciliation_required`; cleanup never deletes the candidate now serving the alias.

## Cleanup

Retain prior generation for a configurable period. Cleanup must refuse to delete the index currently targeted by the alias or an active rebuild target.
