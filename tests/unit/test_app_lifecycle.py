"""Base application startup, liveness, and shutdown behavior."""

import pytest
from fastapi.testclient import TestClient

from event_platform.main import create_app


@pytest.mark.unit
def test_base_app_serves_liveness_and_api_description() -> None:
    app = create_app()

    with TestClient(app) as client:
        liveness = client.get("/health/live")
        assert liveness.status_code == 200
        assert liveness.json() == {"status": "alive"}

        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "/health/live" in openapi.json()["paths"]

        docs = client.get("/docs")
        assert docs.status_code == 200


@pytest.mark.unit
def test_base_app_lifespan_exits_cleanly() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/openapi.json").status_code == 200
