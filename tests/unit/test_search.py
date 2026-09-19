from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.main import create_app
from event_platform.search.search import (
    ElasticsearchSearchService,
    SearchDependencyError,
    SearchQuery,
    decode_search_cursor,
)

pytestmark = pytest.mark.unit


def make_event(number: int) -> CanonicalEvent:
    timestamp = datetime(2026, 1, 1, 12, number, tzinfo=UTC)
    value = EventInput(
        event_type="view",
        timestamp=timestamp,
        user_id="user-1",
        source_url="https://example.test/page",
        metadata={"term": "Café", "nested": {"kind": "One"}},
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        ingested_at=timestamp + timedelta(minutes=1),
    )


class FakeClient:
    def __init__(self, events: list[CanonicalEvent], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    async def search(self, **kwargs: object) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("credentials and endpoint must not leak")
        self.calls.append(kwargs)
        body = kwargs["body"]
        assert isinstance(body, dict)
        size = body["size"]
        assert isinstance(size, int)
        start = 0 if "search_after" not in body else 1
        hits = [
            {
                "_source": event.model_dump(mode="json"),
                "sort": [event.timestamp.isoformat(), str(event.event_id)],
            }
            for event in self.events[start : start + size]
        ]
        return {"hits": {"hits": hits}}


def client_for(service: ElasticsearchSearchService) -> TestClient:
    app = create_app()
    app.state.search_service = service
    return TestClient(app)


@pytest.mark.asyncio
async def test_search_service_builds_fixed_query_and_returns_cursor() -> None:
    fake = FakeClient([make_event(1), make_event(2)])
    service = ElasticsearchSearchService(fake)  # type: ignore[arg-type]
    page = await service.search(
        SearchQuery(
            q="café",
            event_type="view",
            user_id="user-1",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 2, tzinfo=UTC),
            limit=1,
        ),
        request_id=UUID(int=1),
    )
    assert len(page.items) == 1
    assert page.next_cursor
    request = fake.calls[0]
    assert request["index"] == "events-search"
    body = request["body"]
    assert isinstance(body, dict)
    assert body["sort"] == [{"timestamp": "desc"}, {"event_id": "desc"}]
    assert "metadata_text" in repr(body)
    assert "script" not in repr(body)
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"event_type": "view"}} in filters
    assert {"term": {"user_id": "user-1"}} in filters
    assert {
        "range": {
            "timestamp": {
                "gte": datetime(2026, 1, 1, tzinfo=UTC),
                "lte": datetime(2026, 1, 2, tzinfo=UTC),
            }
        }
    } in filters


@pytest.mark.asyncio
async def test_search_cursor_is_filter_bound() -> None:
    fake = FakeClient([make_event(1), make_event(2)])
    service = ElasticsearchSearchService(fake)  # type: ignore[arg-type]
    page = await service.search(SearchQuery(q="café", limit=1), request_id=UUID(int=1))
    assert page.next_cursor
    with pytest.raises(ValueError):
        decode_search_cursor(page.next_cursor, scope=b"different")


@pytest.mark.asyncio
async def test_search_pagination_has_no_duplicate_or_skipped_items() -> None:
    fake = FakeClient([make_event(1), make_event(2)])
    service = ElasticsearchSearchService(fake)  # type: ignore[arg-type]
    first = await service.search(SearchQuery(q="term", limit=1), request_id=UUID(int=1))
    second = await service.search(
        SearchQuery(q="term", limit=1, cursor=first.next_cursor), request_id=UUID(int=1)
    )
    assert [event.event_id for event in first.items + second.items] == [
        make_event(1).event_id,
        make_event(2).event_id,
    ]
    assert second.next_cursor is None
    assert "search_after" in fake.calls[1]["body"]


@pytest.mark.asyncio
async def test_search_dependency_failure_is_safe() -> None:
    service = ElasticsearchSearchService(FakeClient([], fail=True))  # type: ignore[arg-type]
    with pytest.raises(SearchDependencyError, match="search dependency unavailable"):
        await service.search(SearchQuery(q="term"), request_id=UUID(int=1))


@pytest.mark.asyncio
async def test_malformed_search_response_is_classified_as_dependency_failure() -> None:
    class Malformed:
        async def search(self, **kwargs: object) -> dict[str, object]:
            del kwargs
            return {"hits": {"hits": [{"_source": {}, "sort": ["only-one"]}]}}

    service = ElasticsearchSearchService(Malformed())  # type: ignore[arg-type]
    with pytest.raises(SearchDependencyError):
        await service.search(SearchQuery(q="term"), request_id=UUID(int=1))


@pytest.mark.parametrize(
    "query",
    [
        {"q": ""},
        {"q": "x\n"},
        {"q": "x" * 257},
        {"q": "x", "limit": 201},
        {"q": "x", "start": datetime(2026, 1, 1), "end": datetime(2026, 1, 2, tzinfo=UTC)},
        {
            "q": "x",
            "start": datetime(2026, 1, 2, tzinfo=UTC),
            "end": datetime(2026, 1, 1, tzinfo=UTC),
        },
    ],
)
def test_search_query_rejects_unsafe_bounds(query: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SearchQuery.model_validate(query)


def test_search_route_returns_safe_dependency_problem() -> None:
    with client_for(ElasticsearchSearchService(FakeClient([], fail=True))) as client:
        response = client.get("/events/search?q=term")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["retry-after"] == "1"
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert "credentials" not in response.text


def test_search_route_rejects_tampered_cursor() -> None:
    fake = FakeClient([make_event(1), make_event(2)])
    with client_for(ElasticsearchSearchService(fake)) as client:
        first = client.get("/events/search?q=term&limit=1")
        cursor = first.json()["next_cursor"]
        calls_before = len(fake.calls)
        response = client.get(f"/events/search?q=other&limit=1&cursor={cursor}")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert len(fake.calls) == calls_before


def test_search_route_rejects_invalid_query_as_problem() -> None:
    fake = FakeClient([])
    with client_for(ElasticsearchSearchService(fake)) as client:
        response = client.get("/events/search?q=&limit=201")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert fake.calls == []


def test_search_route_rejects_oversized_cursor_before_dependency_call() -> None:
    fake = FakeClient([])
    with client_for(ElasticsearchSearchService(fake)) as client:
        response = client.get("/events/search?q=term&cursor=" + "x" * 513)
    assert response.status_code == 422
    assert fake.calls == []


def test_search_query_rejects_arbitrary_dsl_fields() -> None:
    with pytest.raises(ValueError):
        SearchQuery.model_validate({"q": "term", "script": {"source": "1"}})
