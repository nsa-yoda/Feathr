from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from event_platform.api.routes import query as query_route
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.main import create_app
from event_platform.storage.mongo import EventQuery, MongoDependencyError


def make_event(
    *,
    event_type: str = "view",
    user_id: str = "user-1",
    source_url: str = "https://example.test/path",
    timestamp: datetime,
    event_id: UUID | None = None,
) -> CanonicalEvent:
    input_event = EventInput(
        event_type=event_type,
        timestamp=timestamp,
        user_id=user_id,
        source_url=source_url,
        metadata={"ok": True},
    )
    return CanonicalEvent.from_input(
        input_event,
        event_id=event_id or uuid4(),
        ingested_at=timestamp,
    )


class FakeStore:
    def __init__(
        self,
        events: list[CanonicalEvent],
        *,
        fail: bool = False,
        failure_operation: str = "query_events",
    ) -> None:
        self.events = sorted(
            events,
            key=lambda event: (event.timestamp, event.event_id),
            reverse=True,
        )
        self.fail = fail
        self.failure_operation = failure_operation
        self.queries: list[EventQuery] = []

    async def query(self, query: EventQuery) -> AsyncIterator[CanonicalEvent]:
        self.queries.append(query)
        if self.fail:
            raise MongoDependencyError(self.failure_operation)
        candidates: list[CanonicalEvent] = []
        for event in self.events:
            if query.event_type is not None and event.event_type != query.event_type:
                continue
            if query.user_id is not None and event.user_id != query.user_id:
                continue
            if query.source_url is not None and str(event.source_url) != query.source_url:
                continue
            if query.timestamp_from is not None and event.timestamp < query.timestamp_from:
                continue
            if query.timestamp_to is not None and event.timestamp > query.timestamp_to:
                continue
            if (
                query.after_timestamp is not None
                and query.after_event_id is not None
                and (
                    event.timestamp < query.after_timestamp
                    or (
                        event.timestamp == query.after_timestamp
                        and event.event_id < query.after_event_id
                    )
                )
                is False
            ):
                continue
            candidates.append(event)
        for event in candidates[: query.limit]:
            yield event


def client_for(store: FakeStore) -> TestClient:
    app = create_app()
    app.state.event_store = store
    return TestClient(app)


@pytest.fixture
def events() -> list[CanonicalEvent]:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        make_event(
            timestamp=timestamp,
            event_id=UUID("00000000-0000-0000-0000-000000000003"),
        ),
        make_event(
            timestamp=timestamp,
            event_id=UUID("00000000-0000-0000-0000-000000000002"),
            user_id="user-2",
        ),
        make_event(
            timestamp=timestamp - timedelta(minutes=1),
            event_id=UUID("00000000-0000-0000-0000-000000000001"),
            event_type="purchase",
            source_url="https://example.test/other",
        ),
    ]


def test_query_returns_canonical_items_and_metadata(events: list[CanonicalEvent]) -> None:
    with client_for(FakeStore(events)) as client:
        response = client.get("/events")
    assert response.status_code == 200
    body = response.json()
    assert [item["event_id"] for item in body["items"]] == [str(event.event_id) for event in events]
    assert body["limit"] == 50
    assert body["next_cursor"] is None
    assert UUID(body["request_id"])
    assert all("_id" not in item for item in body["items"])


def test_equal_timestamp_pages_have_no_duplicates_or_holes(events: list[CanonicalEvent]) -> None:
    store = FakeStore(events)
    with client_for(store) as client:
        first = client.get("/events?limit=2")
        second = client.get(f"/events?limit=2&cursor={first.json()['next_cursor']}")
    ids = [item["event_id"] for item in first.json()["items"] + second.json()["items"]]
    assert ids == [str(event.event_id) for event in events]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("event_type=purchase", 1),
        ("user_id=user-2", 1),
        ("source_url=https%3A%2F%2Fexample.test%2Fpath", 2),
        ("start=2026-01-01T00%3A00%3A00Z&end=2026-01-01T00%3A00%3A00Z", 2),
        ("event_type=view&user_id=user-2", 1),
    ],
)
def test_filters_are_forwarded_and_applied(
    query: str, expected: int, events: list[CanonicalEvent]
) -> None:
    with client_for(FakeStore(events)) as client:
        response = client.get(f"/events?{query}")
    assert response.status_code == 200
    assert len(response.json()["items"]) == expected


def test_source_url_filter_uses_canonical_trailing_slash() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    event = make_event(timestamp=timestamp, source_url="https://example.test")
    with client_for(FakeStore([event])) as client:
        response = client.get("/events?source_url=https%3A%2F%2Fexample.test")
    assert response.status_code == 200
    assert [item["event_id"] for item in response.json()["items"]] == [str(event.event_id)]


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=201",
        "start=2026-01-02T00:00:00Z&end=2026-01-01T00:00:00Z",
        "start=2025-01-01T00:00:00Z&end=2026-02-01T00:00:00Z",
        "cursor=not-a-cursor",
        "event_type=" + "x" * 129,
        "user_id=" + "x" * 257,
        "source_url=" + "x" * 2049,
        "event_type=",
        "start=2026-01-01T00:00:00&end=2026-01-01T00:00:00Z",
        "start=2026-01-01T00:00:00%2B02%3A00&end=2026-01-01T00:00:00%2B02%3A00",
        "cursor=.",
        "cursor=" + "a" * 513,
    ],
)
def test_invalid_query_is_safe_problem(query: str, events: list[CanonicalEvent]) -> None:
    store = FakeStore(events)
    with client_for(store) as client:
        response = client.get(f"/events?{query}")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] in {"request_validation_failed", "http_422"}
    assert "not-a-cursor" not in response.text
    assert store.queries == []


def test_tampered_cursor_is_rejected(events: list[CanonicalEvent]) -> None:
    store = FakeStore(events)
    with client_for(store) as client:
        cursor = client.get("/events?limit=1").json()["next_cursor"]
        calls_before = len(store.queries)
        tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
        response = client.get(f"/events?cursor={tampered}")
    assert response.status_code == 422
    assert len(store.queries) == calls_before


def test_cursor_is_bound_to_active_filters(events: list[CanonicalEvent]) -> None:
    with client_for(FakeStore(events)) as client:
        cursor = client.get("/events?limit=1&event_type=view").json()["next_cursor"]
        response = client.get(f"/events?event_type=purchase&cursor={cursor}")
    assert response.status_code == 422


def test_limit_200_is_accepted_and_reported(events: list[CanonicalEvent]) -> None:
    store = FakeStore(events)
    with client_for(store) as client:
        response = client.get("/events?limit=200")
    assert response.status_code == 200
    assert response.json()["limit"] == 200
    assert store.queries[0].limit == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"v": 2, "t": "2026-01-01T00:00:00+00:00", "i": str(uuid4())},
        {"v": 1, "t": "2026-01-01T00:00:00+00:00"},
        {
            "v": 1,
            "t": "2026-01-01T00:00:00+00:00",
            "i": str(uuid4()),
            "extra": True,
        },
        {"v": 1, "t": "2026-01-01T00:00:00+00:00", "i": "not-a-uuid"},
    ],
)
def test_signed_cursor_shape_is_validated(
    payload: dict[str, object], events: list[CanonicalEvent]
) -> None:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(query_route._CURSOR_KEY, raw, hashlib.sha256).digest()
    signature_part = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    with client_for(FakeStore(events)) as client:
        response = client.get(f"/events?cursor={encoded}.{signature_part}")
    assert response.status_code == 422
    assert response.json()["error_code"] == "http_422"
    assert "not-a-uuid" not in response.text


def test_missing_store_and_dependency_failure_are_503(events: list[CanonicalEvent]) -> None:
    app = create_app()
    with TestClient(app) as client:
        missing = client.get("/events")
    assert missing.status_code == 503
    assert missing.headers["retry-after"] == "1"
    with client_for(FakeStore(events, fail=True, failure_operation="decode_event")) as client:
        failed = client.get("/events")
    assert failed.status_code == 503
    assert "Mongo" not in failed.text


def test_empty_result_has_no_cursor(events: list[CanonicalEvent]) -> None:
    with client_for(FakeStore(events)) as client:
        response = client.get("/events?event_type=missing")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["next_cursor"] is None


def test_openapi_declares_query_contract() -> None:
    app = create_app()
    schema = app.openapi()["paths"]["/events"]["get"]
    assert schema["responses"]["200"]["content"]["application/json"]
    assert {"422", "503"}.issubset(schema["responses"])
