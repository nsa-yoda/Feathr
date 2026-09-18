# Feature Request: MongoDB Store and Indexes

## Intent

Implement canonical async persistence/query primitives and initialize only the indexes justified by known access patterns.

## Locked choices

- PyMongo Async API, not Motor.
- MongoDB is canonical.
- Local Docker Mongo runs as a replica set because later Change Streams require it.

## Required repository behavior

- insert canonical event;
- fetch event by immutable ID when resolving duplicate delivery;
- filtered cursor query support used by Feature 008;
- aggregation execution support used by Feature 009 without leaking raw collection access into API routes;
- create/verify required indexes at startup or explicit bootstrap step in an idempotent manner.

## Required indexes

Unique event ID; timestamp+event ID; type+time+ID; user+time+ID; source URL+time+ID. Explain actual key order and verify index names deterministically.

## Deliberately absent

No arbitrary metadata indexes. No wildcard index. No compound index for every optional-filter permutation.

## Failure behavior

Translate PyMongo dependency errors into internal typed errors; do not leak raw exceptions to routes.

## Tests

Real Mongo integration for uniqueness/index presence/query ordering. Unit tests may cover mapping/conversion helpers.


## Dependencies

001, 002

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
