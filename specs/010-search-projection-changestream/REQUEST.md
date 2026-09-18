# Feature Request: Mongo Change-Stream Search Projection

## Intent

Project canonical event inserts into Elasticsearch without coupling ES to ingestion durability.

## Requirements

- watch only relevant events collection operations (primarily inserts for append-only model);
- load persisted resume token/checkpoint at startup when present;
- transform event into ES projection deterministically;
- index using `event_id` as ES `_id`;
- persist new resume token only after all required ES writes for that change succeed;
- on ES transient failure, back off without advancing checkpoint;
- expose last-success time/projection lag approximation/status;
- detect invalid/non-resumable token and fail loudly into reconciliation/rebuild state rather than starting at "now" and losing history.

## Rebuild interaction

When Feature 012 marks a rebuild target active, the projector writes each live change through the normal alias and also directly to the target generation before advancing checkpoint.

## Tests

Projection success/checkpoint ordering; replay idempotency; ES outage does not lose checkpoint; restart resumes; invalid checkpoint path is visible.


## Dependencies

003

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
