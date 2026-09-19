from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.main import create_app
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.rebuild import (
    RebuildError,
    RebuildPhase,
    RebuildRecord,
    RetryPolicy,
    SearchRebuilder,
    build_parser,
    main,
)
from event_platform.storage.rebuilds import MongoRebuildStore

pytestmark = pytest.mark.unit


def event(number: int) -> CanonicalEvent:
    timestamp = datetime(2026, 1, 1, 12, number, tzinfo=UTC)
    value = EventInput(
        event_type="view",
        timestamp=timestamp,
        user_id="user-1",
        source_url="https://example.test/page",
        metadata={"term": "Café", "number": number},
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        ingested_at=timestamp,
    )


class FakeState:
    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired
        self.records: list[RebuildRecord] = []

    async def acquire(self, record: RebuildRecord) -> bool:
        if self.acquired:
            self.records.append(record)
        return self.acquired

    async def save(self, record: RebuildRecord) -> None:
        self.records.append(record)

    async def renew(self, record: RebuildRecord, lease_expires_at: datetime) -> bool:
        del record, lease_expires_at
        return True

    async def latest(self) -> RebuildRecord | None:
        return self.records[-1] if self.records else None


class FakeSearch:
    def __init__(self, *, old: str | None = "events-v000003") -> None:
        self.old = old
        self.created: list[str] = []
        self.batches: list[tuple[str, Sequence[Mapping[str, object]]]] = []
        self.swaps: list[tuple[str, str | None, str]] = []
        self.fail_bulk = False
        self.events: list[str] = []

    async def resolve_alias(self, alias: str) -> str | None:
        del alias
        return self.old

    async def create_index(self, index: str, definition: Mapping[str, object]) -> None:
        assert "mappings" in definition
        self.created.append(index)
        self.events.append("create")

    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int:
        if self.fail_bulk:
            raise RebuildError("bulk_unavailable", transient=True)
        self.events.append("bulk")
        self.batches.append((index, documents))
        return len(documents)

    async def count(self, index: str) -> int:
        return sum(len(batch) for target, batch in self.batches if target == index)

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
        self.swaps.append((alias, old_index, new_index))

    async def delete_index(self, index: str) -> None:
        del index
        self.events.append("delete")


class FakeSource:
    def __init__(self, events: list[CanonicalEvent]) -> None:
        self.events = events

    def scan(self) -> AsyncIterator[CanonicalEvent]:
        async def items() -> AsyncIterator[CanonicalEvent]:
            for item in self.events:
                yield item

        return items()


async def record_target(target: str | None, values: list[str | None]) -> None:
    values.append(target)


async def record_wait(delay: float, values: list[float]) -> None:
    values.append(delay)


@pytest.mark.asyncio
async def test_rebuild_success_activates_live_target_before_scan_and_swaps_atomically() -> None:
    state = FakeState()
    search = FakeSearch()
    target_events: list[str | None] = []

    async def activate(target: str | None) -> None:
        target_events.append(target)
        search.events.append("activate" if target else "deactivate")

    rebuilder = SearchRebuilder(
        state=state,
        search=search,
        source=FakeSource([event(1), event(2)]),
        owner="reviewer",
        set_live_target=activate,
        batch_size=1,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = await rebuilder.run()

    assert result.phase == RebuildPhase.COMPLETED
    assert result.old_index == "events-v000003"
    assert result.target_index == "events-v000004"
    assert result.scanned_count == result.indexed_count == 2
    assert search.swaps == [("events-search", "events-v000003", "events-v000004")]
    assert target_events[0] == "events-v000004"
    assert target_events[-1] is None
    assert search.events.index("activate") < search.events.index("bulk")
    phases = [record.phase for record in state.records]
    required = [
        RebuildPhase.INDEX_CREATING,
        RebuildPhase.BULK_INDEXING,
        RebuildPhase.RECONCILING,
        RebuildPhase.VERIFYING,
        RebuildPhase.SWAPPING,
        RebuildPhase.COMPLETED,
    ]
    positions = [phases.index(phase) for phase in required]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_rebuild_lease_rejection_does_not_create_or_swap_target() -> None:
    state = FakeState(acquired=False)
    search = FakeSearch()
    rebuilder = SearchRebuilder(state=state, search=search, source=FakeSource([]), owner="other")

    with pytest.raises(RebuildError, match="rebuild_lease_unavailable"):
        await rebuilder.run()
    assert search.created == []
    assert search.swaps == []


@pytest.mark.asyncio
async def test_transient_bulk_failures_are_bounded_and_failed_target_is_not_swapped() -> None:
    state = FakeState()
    search = FakeSearch()
    search.fail_bulk = True
    waits: list[float] = []
    rebuilder = SearchRebuilder(
        state=state,
        search=search,
        source=FakeSource([event(1)]),
        owner="reviewer",
        retry_policy=RetryPolicy(max_attempts=2, delay_seconds=0),
        sleep=lambda delay: record_wait(delay, waits),
    )

    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await rebuilder.run()
    assert waits == [0]
    assert search.swaps == []
    assert state.records[-1].phase == RebuildPhase.FAILED


@pytest.mark.asyncio
async def test_count_mismatch_never_swaps_and_deactivates_live_target() -> None:
    class Mismatch(FakeSearch):
        async def count(self, index: str) -> int:
            del index
            return 0

    state = FakeState()
    target_events: list[str | None] = []
    rebuilder = SearchRebuilder(
        state=state,
        search=Mismatch(),
        source=FakeSource([event(1)]),
        owner="reviewer",
        set_live_target=lambda target: record_target(target, target_events),
    )
    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await rebuilder.run()
    assert target_events[-1] is None


def test_cli_requires_confirmation_for_mutating_command() -> None:
    parser = build_parser()
    assert "--confirm" in parser.format_help() or "run" in parser.format_help()
    with pytest.raises(SystemExit, match="--confirm"):
        main(["run"])
    assert main(["status"]) == 0


def test_rebuild_status_route_is_read_only_and_safe() -> None:
    state = FakeState()
    record = RebuildRecord(
        rebuild_id=UUID(int=1),
        phase=RebuildPhase.COMPLETED,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        source_collection="events",
        old_index="events-v000001",
        target_index="events-v000002",
        scanned_count=2,
        indexed_count=2,
        owner="reviewer",
        lease_expires_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )
    state.records.append(record)
    app = create_app()
    app.state.rebuild_store = state
    with TestClient(app) as client:
        response = client.get("/events/search/rebuild")
    assert response.status_code == 200
    assert response.json()["phase"] == "completed"
    assert "metadata" not in response.text


def test_rebuild_status_route_returns_safe_not_found_and_dependency_errors() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/events/search/rebuild").status_code == 503
        app.state.rebuild_store = FakeState()
        assert client.get("/events/search/rebuild").status_code == 404


class FakeMongoCollection:
    def __init__(self, document: Mapping[str, object] | None = None) -> None:
        self.document = document
        self.updated: dict[str, object] | None = None
        self.query: Mapping[str, object] | None = None
        self.modified_count = 1

    async def find_one_and_update(
        self,
        query: Mapping[str, object],
        update: Mapping[str, object],
        **kwargs: object,
    ) -> Mapping[str, object] | None:
        self.query = query
        del kwargs
        values = update["$set"]
        assert isinstance(values, dict)
        self.updated = values
        return values

    async def replace_one(
        self,
        query: Mapping[str, object],
        document: Mapping[str, object],
        **kwargs: object,
    ) -> None:
        del query, kwargs
        self.document = document

    async def update_one(self, query: Mapping[str, object], update: Mapping[str, object]) -> object:
        del query
        if self.document is not None and isinstance(update.get("$set"), dict):
            self.document = {**self.document, **update["$set"]}  # type: ignore[arg-type]
        return self

    async def find_one(self, *args: object, **kwargs: object) -> Mapping[str, object] | None:
        del args, kwargs
        return self.document


@pytest.mark.asyncio
async def test_mongo_rebuild_store_acquires_expired_lease_and_round_trips_status() -> None:
    collection = FakeMongoCollection()
    store = MongoRebuildStore(collection)  # type: ignore[arg-type]
    record = RebuildRecord(
        rebuild_id=UUID(int=9),
        phase=RebuildPhase.ACQUIRING,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_collection="events",
        target_index="events-v000001",
        owner="reviewer",
        lease_expires_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )
    assert await store.acquire(record)
    assert collection.query is not None
    assert "$or" in collection.query
    await store.save(record)
    latest = await store.latest()
    assert latest is not None
    assert latest.rebuild_id == record.rebuild_id
    assert latest.target_index == record.target_index


class FakeIndices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def update_aliases(self, **kwargs: object) -> None:
        self.calls.append(("update_aliases", kwargs))


class FakeClient:
    def __init__(self) -> None:
        self.indices = FakeIndices()


@pytest.mark.asyncio
async def test_elasticsearch_adapter_swaps_alias_atomically_and_omits_missing_old_index() -> None:
    client = FakeClient()
    adapter = ElasticsearchRebuildAdapter(client)  # type: ignore[arg-type]
    await adapter.swap_alias("events-search", "events-v000001", "events-v000002")
    await adapter.swap_alias("events-search", None, "events-v000003")
    first = client.indices.calls[0][1]
    second = client.indices.calls[1][1]
    assert first == {
        "actions": [
            {"remove": {"index": "events-v000001", "alias": "events-search"}},
            {"add": {"index": "events-v000002", "alias": "events-search"}},
        ]
    }
    assert second == {"actions": [{"add": {"index": "events-v000003", "alias": "events-search"}}]}
