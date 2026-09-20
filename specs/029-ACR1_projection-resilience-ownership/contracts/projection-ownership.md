# Projection Ownership Contract

- Canonical Mongo persistence never depends on projection availability.
- Checkpoint writes are ordered after target writes.
- A stale generation cannot replace a newer checkpoint.
- Projection batch APIs reject oversized input before task creation.
