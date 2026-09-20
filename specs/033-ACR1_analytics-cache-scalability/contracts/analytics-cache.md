# Analytics Cache Contract

- At most one same-key refresh runs per process.
- Waiter cancellation does not cancel shared refresh work.
- Redis failure bypasses to bounded canonical aggregation and is observable as bypass.
- Cache payloads are versioned and bounded before use.
