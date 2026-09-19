from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.rebuild import RebuildError, RebuildRecord, SearchRebuilder

pytestmark = pytest.mark.failure


def make_event() -> CanonicalEvent:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return CanonicalEvent.from_input(
        EventInput(
            event_type="view",
            timestamp=timestamp,
            user_id="user-1",
            source_url="https://example.test/page",
            metadata={"term": "Café"},
        ),
        event_id=UUID(int=1),
        ingested_at=timestamp,
    )


class State:
    def __init__(self) -> None:
        self.records: list[RebuildRecord] = []

    async def acquire(self, record: RebuildRecord) -> bool:
        self.records.append(record)
        return True

    async def renew(self, record: RebuildRecord, lease_expires_at: datetime) -> bool:
        del record, lease_expires_at
        return True

    async def save(self, record: RebuildRecord) -> None:
        self.records.append(record)

    async def latest(self) -> RebuildRecord | None:
        return self.records[-1] if self.records else None


class Search:
    def __init__(self) -> None:
        self.alias = "events-v000001"
        self.deleted: list[str] = []

    async def resolve_alias(self, alias: str) -> str | None:
        del alias
        return self.alias

    async def create_index(self, index: str, definition: Mapping[str, object]) -> None:
        del index, definition

    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int:
        del index, documents
        return 1

    async def count(self, index: str) -> int:
        del index
        return 1

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
        del alias, old_index, new_index
        raise RebuildError("alias_swap_failed")

    async def delete_index(self, index: str) -> None:
        self.deleted.append(index)


class Source:
    def scan(self) -> AsyncIterator[CanonicalEvent]:
        async def items() -> AsyncIterator[CanonicalEvent]:
            yield make_event()

        return items()


@pytest.mark.asyncio
async def test_alias_swap_failure_leaves_record_failed_without_claiming_success() -> None:
    state = State()
    search = Search()
    rebuilder = SearchRebuilder(state=state, search=search, source=Source(), owner="reviewer")
    with pytest.raises(RebuildError, match="alias_swap_failed"):
        await rebuilder.run()
    assert state.records[-1].phase == "failed"
    assert all(record.phase != "completed" for record in state.records)
    assert search.alias == "events-v000001"
    assert search.deleted == ["events-v000002"]
