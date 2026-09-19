from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from event_platform.api.routes import stats as stats_route
from event_platform.api.routes.stats import (
    MAX_AGGREGATION_TIME_MS,
    MAX_POINTS,
    AnalyticsRange,
    build_stats_pipeline,
)
from event_platform.main import create_app
from event_platform.storage.mongo import MongoDependencyError


class FakeAggregateStore:
    def __init__(
        self, documents: list[Mapping[str, object]], *, failure: str | None = None
    ) -> None:
        self.documents = documents
        self.failure = failure
        self.pipeline: list[dict[str, object]] | None = None
        self.max_time_ms: int | None = None

    async def aggregate(
        self, pipeline: list[dict[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]:
        self.pipeline = pipeline
        self.max_time_ms = max_time_ms
        if self.failure is not None:
            raise MongoDependencyError(self.failure)
        return self.documents


def client_for(store: FakeAggregateStore) -> TestClient:
    app = create_app()
    app.state.event_store = store
    return TestClient(app)


def document(bucket: datetime, event_type: str, count: int) -> dict[str, object]:
    return {"bucket": bucket, "event_type": event_type, "count": count, "_id": object()}


def test_pipeline_matches_before_grouping_and_sorts_points() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    pipeline = build_stats_pipeline(AnalyticsRange(start=start, end=end), "hour")
    assert list(pipeline[0]) == ["$match"]
    assert pipeline[0]["$match"] == {"timestamp": {"$gte": start, "$lte": end}}
    assert "$dateTrunc" in str(pipeline[1]["$group"])
    assert pipeline[-2] == {"$sort": {"bucket": 1, "event_type": 1}}
    assert pipeline[-1] == {"$limit": MAX_POINTS + 1}
    assert "$project" in pipeline[2]


@pytest.mark.parametrize("bucket", ["hour", "day", "week"])
def test_pipeline_supports_all_buckets(bucket: str) -> None:
    start = datetime(2026, 1, 5, tzinfo=UTC)
    truncation = build_stats_pipeline(
        AnalyticsRange(start=start, end=start + timedelta(days=1)),
        bucket,  # type: ignore[arg-type]
    )[1]["$group"]
    rendered = str(truncation)
    assert f"'unit': '{bucket}'" in rendered
    if bucket == "week":
        assert "'startOfWeek': 'monday'" in rendered


def test_explicit_range_returns_ordered_self_describing_points() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store = FakeAggregateStore(
        [
            document(start, "signup", 1),
            document(start, "pageview", 4),
        ]
    )
    with client_for(store) as client:
        response = client.get(
            "/events/stats?bucket=day&start=2026-01-01T00:00:00Z&end=2026-01-02T00:00:00Z"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["bucket"] == "day"
    assert body["timezone"] == "UTC"
    assert body["start"] == "2026-01-01T00:00:00Z"
    assert body["end"] == "2026-01-02T00:00:00Z"
    assert [point["event_type"] for point in body["points"]] == ["pageview", "signup"]
    assert UUID(body["request_id"])
    assert "_id" not in body
    assert store.pipeline is not None
    assert store.max_time_ms == MAX_AGGREGATION_TIME_MS


def test_default_range_is_previous_24_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(stats_route, "_utc_now", lambda: fixed_now)
    store = FakeAggregateStore([])
    with client_for(store) as client:
        response = client.get("/events/stats")
    assert response.status_code == 200
    assert response.json()["bucket"] == "hour"
    assert response.json()["start"] == "2026-01-31T12:00:00Z"
    assert response.json()["end"] == "2026-02-01T12:00:00Z"


def test_empty_range_returns_empty_points() -> None:
    store = FakeAggregateStore([])
    with client_for(store) as client:
        response = client.get("/events/stats?start=2026-01-01T00:00:00Z&end=2026-01-01T00:00:00Z")
    assert response.status_code == 200
    assert response.json()["points"] == []


@pytest.mark.parametrize(
    "query",
    [
        "bucket=minute",
        "start=2026-01-01T00:00:00Z",
        "end=2026-01-01T00:00:00Z",
        "start=2026-01-02T00:00:00Z&end=2026-01-01T00:00:00Z",
        "start=2025-01-01T00:00:00Z&end=2026-02-01T00:00:00Z",
        "start=2026-01-01T00:00:00&end=2026-01-01T00:00:00Z",
        "start=2026-01-01T00:00:00%2B02:00&end=2026-01-01T01:00:00%2B02:00",
    ],
)
def test_invalid_bucket_or_range_is_safe_problem(query: str) -> None:
    with client_for(FakeAggregateStore([])) as client:
        response = client.get(f"/events/stats?{query}")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 422
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "2026-01-02" not in response.text


def test_missing_store_returns_retryable_problem() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/events/stats")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("failure", ["aggregate_events", "decode_analytics"])
def test_storage_and_decode_failures_are_safe(failure: str) -> None:
    with client_for(FakeAggregateStore([], failure=failure)) as client:
        response = client.get("/events/stats")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 503
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert failure not in response.text
    assert "Mongo" not in response.text


def test_malformed_aggregation_point_is_503() -> None:
    store = FakeAggregateStore([{"bucket": "not-a-date", "event_type": "view", "count": 1}])
    with client_for(store) as client:
        response = client.get("/events/stats")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 503
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_naive_bson_bucket_is_treated_as_utc() -> None:
    store = FakeAggregateStore([{"bucket": datetime(2026, 1, 1), "event_type": "view", "count": 1}])
    with client_for(store) as client:
        response = client.get("/events/stats")
    assert response.status_code == 200
    assert response.json()["points"][0]["bucket"] == "2026-01-01T00:00:00Z"


def test_result_cardinality_is_bounded_without_partial_counts() -> None:
    store = FakeAggregateStore(
        [document(datetime(2026, 1, 1, tzinfo=UTC), "view", 1)] * (MAX_POINTS + 1)
    )
    with client_for(store) as client:
        response = client.get("/events/stats")
    assert response.status_code == 422
    assert response.json()["status"] == 422
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_openapi_declares_stats_contract() -> None:
    schema = create_app().openapi()["paths"]["/events/stats"]["get"]
    assert schema["responses"]["200"]["content"]["application/json"]
    assert {"422", "503"}.issubset(schema["responses"])
