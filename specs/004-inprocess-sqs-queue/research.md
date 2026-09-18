# Feature 004 Research

- `asyncio.Condition` coordinates producers and consumers without busy loops; timed waits cover long polling, capacity, and visibility deadlines.
- A monotonic clock is injected so visibility and timeout behavior can be tested without wall-clock sleeps.
- Delivery bodies are recursively frozen at send time. Receipt handles are random opaque UUID strings and are never derived from body data.
- The implementation keeps the port independent of HTTP, Mongo, and the future SQS adapter.
