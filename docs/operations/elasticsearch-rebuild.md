# Elasticsearch Rebuild Runbook

The repository provides an explicit read-only status CLI and a guarded run entry point:

```bash
uv run --locked python -m event_platform.cli search rebuild-status
uv run --locked python -m event_platform.cli search rebuild --confirm
```

`rebuild-status` reads the durable Mongo record and prints a safe JSON status (or
`{"status":"not_found"}`). The mutating `rebuild --confirm` command remains an
application-harness boundary: use the HTTP/runtime orchestration in the deployed app
until a separate operator process supplies the same Mongo, Elasticsearch, and source
dependencies. README and UI/status use the same route and state model.

## Operator expectations

- starting a rebuild returns/displays a `rebuild_id`;
- a second rebuild cannot run concurrently;
- current alias remains serving until verification passes;
- progress is visible through logs/status/metrics;
- failures retain diagnostic state and do not alter the alias;
- previous index is retained for configured rollback window;
- cleanup of old generations is explicit and safe.

Do not tell reviewers to manually delete the ES index as the normal recovery procedure.
