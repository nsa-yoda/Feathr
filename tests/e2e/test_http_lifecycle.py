"""Critical user-visible lifecycle against a running application stack."""

import os
import time
from uuid import uuid4

import httpx
import pytest


def _wait_for(
    client: httpx.Client, path: str, predicate: object, timeout: float = 30.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        response = client.get(path)
        last = response.text
        if response.status_code == 200:
            payload = response.json()
            if callable(predicate) and predicate(payload):
                return payload
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {path}; last response={last[:500]}")


@pytest.mark.e2e
def test_ingestion_idempotency_projection_and_analytics_lifecycle() -> None:
    base_url = os.environ.get("E2E_BASE_URL")
    if not base_url:
        pytest.fail("E2E_BASE_URL is required for the black-box E2E suite")
    suffix = uuid4().hex
    payload = {
        "event_type": "e2e.event",
        "timestamp": "2026-01-01T00:00:00Z",
        "user_id": f"e2e-{suffix}",
        "source_url": "https://example.invalid/e2e",
        "metadata": {"suite": "e2e", "marker": suffix},
    }
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        headers = {"Idempotency-Key": f"e2e-{suffix}"}
        accepted = client.post("/events", json=payload, headers=headers)
        replay = client.post("/events", json=payload, headers=headers)
        assert accepted.status_code == 202
        assert replay.status_code == 202
        event_id = accepted.json()["event_id"]
        assert replay.json()["event_id"] == event_id

        _wait_for(
            client,
            f"/events?user_id=e2e-{suffix}&limit=50",
            lambda body: any(item["event_id"] == event_id for item in body.get("items", [])),
        )
        _wait_for(
            client,
            f"/events/search?q={suffix}&limit=50",
            lambda body: any(item["event_id"] == event_id for item in body.get("items", [])),
        )
        stats = _wait_for(
            client, "/events/stats?bucket=hour", lambda body: bool(body.get("points"))
        )
        realtime = _wait_for(
            client,
            "/events/stats/realtime?window_minutes=5",
            lambda body: body.get("by_event_type", {}).get("e2e.event", 0) > 0,
        )
        assert stats["points"]
        assert realtime["by_event_type"]["e2e.event"] > 0
