# Feature 004 Quickstart

Construct `InProcessQueue(capacity=100, visibility_timeout=30, send_timeout=1)`, `await send(body)`, `await receive(long_poll=20)`, and `await delete(delivery.message_id, delivery.receipt_handle)`. Inject `clock=` in deterministic tests and call `wake()` after advancing it.
