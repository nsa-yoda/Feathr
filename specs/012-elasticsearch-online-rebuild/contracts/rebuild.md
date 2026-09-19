# Feature 012 Rebuild Contract

- `GET /events/search/rebuild` returns the latest durable rebuild status or 404 when none exists.
- `python -m event_platform.search.rebuild --help` documents the status and guarded run command.
- `python -m event_platform.search.rebuild run` requires an explicit `--confirm` flag; the HTTP API does not trigger rebuilds.
- A failed or unverified run returns a safe failed status and leaves the current alias target unchanged.
