# Lifecycle Contract

- `request_shutdown()` first rejects new queue admission.
- Drainable persistence tasks continue consuming until queue depth and in-flight work reach zero or the grace deadline expires.
- Non-drainable derived tasks stop promptly.
- A degradable task failure changes only that component's status; a critical failure changes global lifecycle state and stops admission.
- Shutdown output contains queue residuals, task outcomes, and whether the drain completed cleanly.
