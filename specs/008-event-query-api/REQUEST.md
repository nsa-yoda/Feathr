# Feature Request: Event Query API

## Endpoint

`GET /events`

## Filters

Optional event type, start/end, user ID, exact source URL. Define invalid combinations and range limits.

## Pagination

Keyset pagination sorted `(timestamp DESC, event_id DESC)`. Cursor is opaque/versioned and tamper/shape validated. Default and maximum limits are explicit (target default 50, max 200 unless clarified otherwise).

## Response

Items, page metadata, optional `next_cursor`; never return internal Mongo `_id` unless intentionally part of the contract.

## Semantics

Canonical Mongo results may contain events not yet searchable in Elasticsearch. This is expected.

## Tests

Every single filter, representative combinations, boundaries with identical timestamps, no duplicates/holes while paginating a static dataset, malformed cursor, max limit, source URL normalization.


## Dependencies

003

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
