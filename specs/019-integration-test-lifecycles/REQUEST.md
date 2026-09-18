# Feature Request: Integration Test Lifecycles

## Intent

Use real services and prove the system's cross-component contracts.

## Required scenarios

1. POST event -> async worker -> GET /events returns canonical event.
2. POST event -> Mongo Change Stream -> ES -> GET /events/search finds metadata term.
3. seed multiple event types/times -> GET /events/stats correct grouping.
4. realtime stats -> first miss then hit with same logical result.
5. duplicate/redelivery -> one Mongo event.
6. online ES rebuild -> alias changes and all prior + live events remain searchable.

## Harness

Tests may target an ephemeral Compose stack or testcontainers, but must actually use Mongo replica set, Elasticsearch, and Redis. Provide deterministic setup/cleanup and unique test namespaces/index prefixes when necessary.

## Async assertions

Use poll-until helpers with explicit deadline/interval and diagnostic timeout messages, never `sleep(5)` as synchronization.


## Dependencies

003, 005, 006, 008, 009, 010, 011, 013

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
