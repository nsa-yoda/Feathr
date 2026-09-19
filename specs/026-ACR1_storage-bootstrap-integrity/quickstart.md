# Quickstart: Validate Storage Bootstrap Integrity

## Isolated checks

```bash
uv run --locked pytest -q \
  tests/unit/test_storage_bootstrap.py \
  tests/unit/test_storage_bootstrap_cli.py \
  tests/unit/test_app_settings.py \
  tests/unit/test_app_lifecycle.py
uv run --locked ruff check src tests
uv run --locked mypy
```

Expected result: the manifest, verifier, CLI, production setting, and lifespan tests pass without an external service.

## Real Mongo lifecycle

Start the repository Mongo replica set or supply an equivalent test endpoint, then run:

```bash
MONGO_URI='mongodb://127.0.0.1:27017/?replicaSet=rs0' \
  uv run --locked pytest -q tests/integration/test_storage_bootstrap_integration.py -m integration
```

The test uses a unique database, bootstraps it without test-side index creation, verifies all declared structures, proves `event_id` uniqueness, checks idempotent repeat bootstrap, and confirms missing or incompatible state fails verification. Cleanup runs in `finally`.

## Operator commands

With `EVENT_PLATFORM_MONGO_URL` and `EVENT_PLATFORM_MONGO_DATABASE` configured:

```bash
uv run --locked python -m event_platform.cli storage bootstrap
uv run --locked python -m event_platform.cli storage verify
```

Both commands must report schema version 1 and the same manifest fingerprint. The verification command performs no writes.

## Compose acceptance

```bash
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example up --build -d
make smoke
```

Inspect `docker compose ps`: `storage-bootstrap` must have completed successfully before `app` becomes healthy.
