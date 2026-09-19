# Feature 020 Quickstart

## Run the deterministic failure selection

```bash
pytest -q tests/failure -m failure
```

The selection uses explicit fake ports and does not require `MONGO_URI`, `ELASTICSEARCH_URL`, or `REDIS_URL`. It proves Mongo retry/readiness/queue behavior, post-insert redelivery, DLQ exhaustion, ES checkpoint/recovery and invalid-resume handling, Redis bypass/fallback, queue saturation, and rebuild alias safety.

Run `make test-failure` for the repository gate. The exact passing count is recorded in `CODEX_WORK.LOG`, `docs/requirements-traceability.md`, `docs/ai-workflow-log.md`, and the Feature 020 review report. Feature 019 remains the source of real-service integration evidence; deterministic failure tests do not replace those service-backed runs.
