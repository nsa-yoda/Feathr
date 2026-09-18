# Consistency Model

## MongoDB

Canonical persistence is the point at which a queue message is safely acknowledged by the local worker. Canonical GET and aggregation endpoints observe MongoDB state.

## Elasticsearch

Eventual consistency. A persisted event can be returned by `GET /events` before `GET /events/search` can find it. APIs and tests must use bounded polling when asserting search visibility.

Projection is at-least-once from the application's perspective. Duplicate projection deliveries are harmless because ES document IDs are immutable `event_id` values.

## Redis

Realtime statistics may be stale up to approximately the configured TTL plus computation/network delay. Cache contents are never authoritative.

## Queue

At-least-once redelivery while the process remains alive. Process restart can drop messages not yet persisted. Never describe this as exactly-once or durable acceptance.
