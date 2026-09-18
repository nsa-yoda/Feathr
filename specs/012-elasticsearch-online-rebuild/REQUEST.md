# Feature Request: Online Elasticsearch Rebuild

## Intent

Make Elasticsearch fully rebuildable from MongoDB with no planned search downtime and complete operational history.

## Required state

Mongo-backed rebuild record/lease with `rebuild_id`, phase, started/completed timestamps, source collection, old index, target index, counts, failures, and lease expiry/owner.

## Algorithm

1. acquire exclusive leased lock;
2. resolve current alias target;
3. create next versioned physical index with current desired mapping/settings;
4. mark target as active rebuild target so live projector dual-writes;
5. bulk scan canonical Mongo and bulk index target idempotently;
6. retry bounded transient bulk failures and record permanent failures;
7. reconcile/verify target has converged with canonical state and live projection lag is caught up;
8. atomically remove alias from old and add alias to new in one aliases request;
9. mark rebuild completed and clear dual-write target;
10. retain old generation for configurable rollback/cleanup period.

## Safety invariants

Never swap a failed/unverified target. If the rebuild crashes, next operator/run can detect stale lease/state and resume or safely restart. Current alias remains serving until verified swap.

## Interface

Provide a documented CLI command suitable for reviewer use. A read-only status endpoint feeds the UI. A dangerous rebuild HTTP action is optional and must be disabled/protected by default if implemented.

## Logs/metrics

Every phase change logged with rebuild ID. Progress counts are metrics/logs without per-document spam.

## Tests

Successful rebuild and alias swap; live writes during rebuild visible after swap; ES failure leaves old alias; stale lock recovery; count/failure verification prevents unsafe swap.


## Dependencies

010, 011

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
