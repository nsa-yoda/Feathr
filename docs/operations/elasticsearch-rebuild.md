# Elasticsearch Rebuild Runbook

The repository provides an explicit read-only status CLI and a guarded run entry point:

```bash
uv run --locked python -m event_platform.cli search rebuild-status
uv run --locked python -m event_platform.cli search rebuild --confirm
```

`rebuild-status` reads the durable Mongo record and prints a safe JSON status (or
`{"status":"not_found"}`). The mutating `rebuild --confirm` command constructs
the Mongo canonical source, projector, rebuild lease/state store, and Elasticsearch
adapter itself. Run it only while the MongoDB replica set and Elasticsearch are
reachable. It activates projector dual-write, captures a Mongo ObjectId high-water
boundary, waits for projector convergence, verifies event identities, and swaps the
stable alias with one Elasticsearch aliases request.

## Operator expectations

- starting a rebuild returns/displays a `rebuild_id`;
- a second rebuild cannot run concurrently;
- current alias remains serving until verification passes;
- progress is visible through logs/status/metrics;
- failures retain diagnostic state and do not alter the alias;
- post-alias state persistence failures record `reconciliation_required` and never
  delete the newly serving generation;
- previous index is retained for configured rollback window;
- cleanup of old generations is explicit and safe.

## Service-backed acceptance evidence

With the Compose stack running, execute:

```bash
MONGO_URI='mongodb://localhost:27017/?replicaSet=rs0&directConnection=true' \
ELASTICSEARCH_URL='http://localhost:9200' \
.venv/bin/pytest -q tests/integration/test_rebuild_live.py
```

The lifecycle test pauses the first canonical backfill scan, writes D/E/F while
the candidate is dual-written, proves the high-water/projector checkpoint
convergence and identity set, observes one atomic alias swap, writes G after
cutover, and exercises verification, alias-swap, and post-swap persistence
failures. The test skips only when these explicitly supplied services are not
available.

Do not tell reviewers to manually delete the ES index as the normal recovery procedure.
