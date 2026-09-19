# Feature 015 Quickstart

1. Start the API with `make run` or the documented local command.
2. Call `/health/live`, `/health/ready`, and `/health/components`; verify
   readiness follows the Mongo and worker probes while ES/Redis degradation is
   reported separately.
3. Call `/metrics` after a few requests and confirm route/status families contain
   no raw identifiers.
4. Run `.venv/bin/pytest -q tests/unit/test_request_id.py tests/unit/test_observability_health.py`.
