from __future__ import annotations

from uuid import UUID

import pytest

from event_platform.search.search import (
    ElasticsearchSearchService,
    SearchDependencyError,
    SearchQuery,
)

pytestmark = pytest.mark.failure


@pytest.mark.asyncio
async def test_search_transport_failure_does_not_expose_driver_details() -> None:
    class Outage:
        async def search(self, **kwargs: object) -> object:
            del kwargs
            raise RuntimeError("password=secret endpoint=https://private.example")

    with pytest.raises(SearchDependencyError) as raised:
        await ElasticsearchSearchService(Outage()).search(
            SearchQuery(q="term"), request_id=UUID(int=1)
        )  # type: ignore[arg-type]
    assert "secret" not in str(raised.value)
