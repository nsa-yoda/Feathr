# Elasticsearch Rebuild Runbook

The final implementation must provide an explicit CLI, for example:

```bash
uv run python -m event_platform.cli search rebuild
uv run python -m event_platform.cli search rebuild-status
```

Exact spelling may evolve, but README and UI/status must agree.

## Operator expectations

- starting a rebuild returns/displays a `rebuild_id`;
- a second rebuild cannot run concurrently;
- current alias remains serving until verification passes;
- progress is visible through logs/status/metrics;
- failures retain diagnostic state and do not alter the alias;
- previous index is retained for configured rollback window;
- cleanup of old generations is explicit and safe.

Do not tell reviewers to manually delete the ES index as the normal recovery procedure.
