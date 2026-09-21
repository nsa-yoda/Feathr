"""Contracts for the repository-owned latency and bounded-load harness."""

from __future__ import annotations

import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts/performance"
HARNESS = runpy.run_path(str(SCRIPT))


def test_percentile_and_positive_integer_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    percentile = HARNESS["percentile"]
    positive_int = HARNESS["positive_int"]
    assert percentile([1.0, 4.0, 2.0, 3.0], 50) == 3.0
    assert percentile([1.0, 4.0, 2.0, 3.0], 99) == 4.0
    monkeypatch.setenv("PERF_REQUESTS", "0")
    with pytest.raises(ValueError, match="must be positive"):
        positive_int("PERF_REQUESTS", 20)


class _Response:
    def __init__(self, body: Mapping[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Mapping[str, Any]:
        return self._body


class _PagedClient:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, str | int]] = []

    async def get(self, _path: str, *, params: Mapping[str, str | int]) -> _Response:
        self.calls.append(params)
        if "cursor" not in params:
            return _Response(
                {"items": [{"event_id": "a"}, {"event_id": "b"}], "next_cursor": "next"}
            )
        return _Response({"items": [{"event_id": "c"}], "next_cursor": None})


@pytest.mark.asyncio
async def test_event_identity_reconciliation_consumes_all_cursor_pages() -> None:
    client = _PagedClient()
    collect_event_ids = HARNESS["collect_event_ids"]
    event_ids = await collect_event_ids(
        client,
        "/events",
        params={"user_id": "isolated-load-run", "limit": 200},
    )
    assert event_ids == {"a", "b", "c"}
    assert client.calls[1]["cursor"] == "next"


def test_load_profile_is_bounded_and_requires_end_to_end_visibility() -> None:
    source = SCRIPT.read_text()
    assert 'positive_int("PERF_REQUESTS", 500 if load_profile else 20)' in source
    assert 'positive_int("PERF_CONCURRENCY", 50 if load_profile else 1)' in source
    assert "expected_ids <= canonical_ids" in source
    assert "expected_ids <= search_ids" in source
    assert '"ingest_throughput_per_second"' in source
    assert '"error_rate"' in source
