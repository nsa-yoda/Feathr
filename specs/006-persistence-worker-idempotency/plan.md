# Implementation Plan: Persistence Worker and Idempotency

Implement a pure async worker around `InProcessQueue` and `MongoEventStore`. Decode canonical envelopes, insert, verify duplicates by payload hash, classify conflicts, expose immutable metrics, and provide bounded worker-loop concurrency. Keep DLQ policy in Feature 007.
