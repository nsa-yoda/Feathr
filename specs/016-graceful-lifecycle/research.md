# Feature 016 Research

1. Queue admission must be distinct from queue closure so workers can drain
   visible messages without accepting new API work.
2. `asyncio.wait_for` around a gathered task set provides a deterministic grace
   deadline; cancelled tasks must be gathered to avoid leaks.
3. Resource close callbacks are injected for tests and keep driver-specific
   lifecycle concerns out of the supervisor state machine.
