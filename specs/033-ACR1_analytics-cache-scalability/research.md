# Research

Realtime statistics already had per-key locks and an in-flight task map. Awaiting the task directly allowed cancellation propagation from one caller to all waiters. `asyncio.shield` is the narrow fix and keeps task ownership explicit.
