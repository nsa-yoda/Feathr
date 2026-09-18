# Feature 006 Research

- The queue's receipt handle is the ack authority; `delete` is called only after Mongo insert or same-hash verification.
- Mongo remains canonical and the worker never uses Redis for correctness.
- The conflict hook is intentionally narrow so Feature 007 can add DLQ policy without changing persistence semantics.
- Queue volatility limits pre-enqueue idempotency-key collapse; event identity and payload hash remain the durable safety boundary.
