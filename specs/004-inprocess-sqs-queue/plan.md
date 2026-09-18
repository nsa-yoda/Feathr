# Implementation Plan: In-Process SQS-Style Queue

Use an `asyncio.Condition`, injectable monotonic clock, recursively frozen message bodies, opaque per-delivery receipts, bounded sends, long-poll receives, visibility expiry, safe stats, and an inspectable DLQ. Keep the queue independent of service lifespan and external dependencies.
