from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from elasticsearch import AsyncElasticsearch

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.mapping import INDEX_MAPPING, index_name
from event_platform.search.projection import (
    ChangeStreamEvent,
    ProjectionCheckpoint,
    SearchProjector,
)
from event_platform.search.search import ElasticsearchSearchService, SearchQuery

pytestmark = pytest.mark.integration


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


@pytest.mark.skipif(
    not os.getenv("ELASTICSEARCH_URL"),
    reason="ELASTICSEARCH_URL is not configured",
)
@pytest.mark.asyncio
async def test_real_elasticsearch_mapping_and_search_path() -> None:
    """Exercise mapping creation, metadata search, filters, and pagination."""

    client = AsyncElasticsearch(os.environ["ELASTICSEARCH_URL"])
    suffix = uuid4().hex[:8]
    physical = index_name(f"events-test-{suffix}")
    alias = f"events-search-test-{suffix}"
    try:
        try:
            await client.info()
        except Exception as error:  # pragma: no cover - service-gated environment
            pytest.skip(f"Elasticsearch is unavailable: {type(error).__name__}")
        await client.indices.create(
            index=physical,
            settings=INDEX_MAPPING["settings"],
            mappings=INDEX_MAPPING["mappings"],
        )
        await client.indices.put_alias(index=physical, name=alias)
        first = make_event(1)
        second = make_event(2)

        class MemoryCheckpoint:
            def __init__(self) -> None:
                self.value: ProjectionCheckpoint | None = None

            async def load(self, projector: str) -> ProjectionCheckpoint | None:
                del projector
                return self.value

            async def save(self, checkpoint: ProjectionCheckpoint) -> None:
                self.value = checkpoint

        projector = SearchProjector(
            projector="events-search-live",
            checkpoint=MemoryCheckpoint(),
            writer=ElasticsearchProjectionWriter(client, alias=alias),
        )
        await projector.start()
        await projector.project_change(ChangeStreamEvent({"_data": "one"}, first))
        await projector.project_change(ChangeStreamEvent({"_data": "two"}, second))
        await client.indices.refresh(index=physical)

        service = ElasticsearchSearchService(client, alias=alias)
        page = await service.search(SearchQuery(q="cafe", limit=1), request_id=UUID(int=3))
        assert [item.event_id for item in page.items] == [second.event_id]
        assert page.next_cursor
        next_page = await service.search(
            SearchQuery(q="CAFE", limit=1, cursor=page.next_cursor), request_id=UUID(int=3)
        )
        assert [item.event_id for item in next_page.items] == [first.event_id]
        assert next_page.next_cursor is None
    finally:
        try:
            await client.indices.delete(index=physical, ignore_unavailable=True)
        except Exception:
            pass
        try:
            await client.indices.delete_alias(index=physical, name=alias, ignore_unavailable=True)
        except Exception:
            pass
        await client.close()
