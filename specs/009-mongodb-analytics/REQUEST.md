# Feature Request: MongoDB Analytics

## Endpoint

`GET /events/stats`

## Behavior

Mongo aggregation counts events grouped by `event_type` and time bucket `hour|day|week` using `$dateTrunc`. Default timezone UTC. Bound date ranges to prevent accidental full-history abuse.

## Pipeline shape

Apply `$match` as early as possible, then `$dateTrunc`/`$group`, then stable sort. Do not load raw events into Python to aggregate.

## Response

Self-describing effective range, bucket, timezone, and ordered data points.

## Edge cases

Empty ranges, boundary timestamps, week definition, DST if timezone configurability is added, invalid start>end.

## Tests

Real Mongo aggregation with known timestamps crossing hour/day/week boundaries and multiple event types.


## Dependencies

003

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
