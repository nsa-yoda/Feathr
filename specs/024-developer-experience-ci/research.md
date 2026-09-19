# Feature 024 Research

- `uv.lock` is checked in and `pyproject.toml` supports Python 3.12+.
- Existing Make targets cover static/unit/integration/failure/coverage/smoke/Postman but lack aggregate, Compose lifecycle, and rebuild targets.
- `docker compose config --quiet` is Docker-free and suitable for CI validation; live Compose/Postman are separate runtime gates.
- `event_platform.cli search rebuild-status` is the read-only rebuild inspection command; `search rebuild --confirm` is guarded and mutating.
