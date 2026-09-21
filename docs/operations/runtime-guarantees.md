# Runtime Guarantees and Failure Dispositions

## Accepted events and shutdown

`POST /events` returns `202` only after validation and in-process queue admission.
During graceful shutdown the API stops new admission first, then leaves the
drainable persistence worker running until accepted queue depth and in-flight work
reach zero or `EVENT_PLATFORM_SHUTDOWN_GRACE_PERIOD` expires. The structured
`lifecycle.queue_depth` event records residual volatile work when the deadline is
exceeded. A process crash can still lose messages that were only in the in-process
queue; an SQS/Kafka-equivalent is the production migration path.

## Derived services

Elasticsearch projection and Redis cache/rate-limit state are derived. A projector
owns a Mongo lease with a fencing generation and must renew it before checkpointing.
Lease release keeps an expired generation tombstone, and startup raises a newly
created legacy lease above any surviving checkpoint generation, so a restart cannot
reuse a fencing number and strand the projector.
If Elasticsearch exits, the lifecycle marks search degraded while Mongo ingestion and
canonical readiness continue. Redis outages use the bounded local leaky bucket and
cache bypass behavior.

## Producer idempotency

Idempotency records are scoped by the authenticated client token when production auth
is enabled, and by the documented local single-client scope otherwise. Reservations
carry an owner token and generation. Queue admission failure releases only the matching
reservation, stale takeover is a Mongo compare-and-set, and completion cannot be
written by a stale owner.

## Rate limiting

Redis performs the distributed leaky-bucket reservation. A process-wide delayed-request
gate, configured by `EVENT_PLATFORM_RATE_LIMIT_MAX_DELAYED_REQUESTS`, bounds memory and
waiting tasks. `429` is reserved for a full bounded backlog; route classification treats
`/events/search` and analytics as expensive operations.

## Operational limitations

The assignment intentionally keeps the in-process queue and static bearer-token
boundary. A production deployment should move queue durability to SQS/Kafka and place
tenant/role authorization behind a trusted identity edge. High-volume analytics should
move from repeated range aggregation to materialized time buckets when measurements
show that Mongo scans are the bottleneck.
