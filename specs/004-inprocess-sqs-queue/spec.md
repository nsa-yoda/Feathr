---
description: "Bounded SQS-style in-process queue with visibility and redelivery"
---

# Feature Specification: In-Process SQS-Style Queue

**Feature Branch**: `004-inprocess-sqs-queue`  
**Created**: 2026-09-18  
**Status**: Ready for review

## Clarifications

- Queue capacity counts all queued and in-flight messages. `send` waits only up to its configured timeout.
- A receive creates a new opaque receipt handle on every delivery attempt; the prior handle is invalid immediately.
- Visibility uses an injectable monotonic clock. A public wake hook lets deterministic tests notify the queue after advancing a fake clock.
- Redrive moves visible messages whose receive count reaches the configured threshold to an inspectable in-memory DLQ.

## Functional Requirements

- **FR-001**: The queue MUST expose async send, long-poll receive, delete by current receipt handle, visibility change, stats, redrive, and close operations behind a port-like class.
- **FR-002**: Capacity MUST be bounded and sends MUST honor a timeout without busy-looping.
- **FR-003**: Receive MUST make a message invisible until its visibility deadline, increment receive count, and rotate the receipt handle on redelivery.
- **FR-004**: Delete and visibility changes MUST reject stale or unknown receipt handles.
- **FR-005**: Close MUST wake waiters and predictably reject new sends/receives while allowing already returned deliveries to be deleted.
- **FR-006**: Stats and DLQ inspection MUST be concurrency-safe and must not expose mutable internal message state.

## Success Criteria

- Send/receive/delete, stale receipt rejection, expiry redelivery, long poll, capacity timeout, concurrent consumers, close, and redrive all have deterministic tests.
- No queue operation uses a polling sleep or blocking synchronization.
