# Quickstart

Run `.venv/bin/pytest -q tests/unit/test_lifecycle.py tests/unit/test_persistence_worker.py tests/unit/test_app_settings.py`.

The integration behavior is service-independent for the in-process queue; real Mongo delivery remains covered by the existing integration lifecycle suite when `MONGO_URI` is configured.
