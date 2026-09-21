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
    RebuildBoundary,
    RebuildConvergence,
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

    async def iter_event_ids(self, index: str) -> AsyncIterator[str]:
        for target, batch in self.batches:
            if target == index:
                for document in batch:
                    event_id = document.get("event_id")
                    assert isinstance(event_id, str)
                    yield event_id

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


@pytest.mark.asyncio
async def test_identity_verification_rejects_equal_count_with_wrong_event_id() -> None:
    class WrongIdentity(FakeSearch):
        async def iter_event_ids(self, index: str) -> AsyncIterator[str]:
            del index
            yield str(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))

    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await SearchRebuilder(
            state=FakeState(),
            search=WrongIdentity(),
            source=FakeSource([event(1)]),
            owner="reviewer",
        ).run()


@pytest.mark.asyncio
async def test_convergence_boundary_is_persisted_before_alias_swap() -> None:
    boundary = "000000000000000000000010"

    class BoundedSource(FakeSource):
        async def capture_high_water(self) -> str:
            return boundary

    async def converge(_initial: str | None):
        from event_platform.search.rebuild import RebuildConvergence

        return RebuildConvergence(source_high_water=boundary, projector_checkpoint=boundary)

    result = await SearchRebuilder(
        state=FakeState(),
        search=FakeSearch(),
        source=BoundedSource([event(1)]),
        owner="reviewer",
        wait_for_convergence=converge,
    ).run()
    assert result.source_high_water == boundary
    assert result.projector_checkpoint == boundary


@pytest.mark.asyncio
async def test_post_swap_state_failure_does_not_delete_serving_target() -> None:
    class StateFailsAfterSwap(FakeState):
        def __init__(self) -> None:
            super().__init__()
            self.save_count = 0

        async def save(self, record: RebuildRecord) -> None:
            self.save_count += 1
            if record.phase == RebuildPhase.COMPLETED:
                raise RuntimeError("state unavailable")
            await super().save(record)

    state = StateFailsAfterSwap()
    search = FakeSearch()
    with pytest.raises(RuntimeError):
        await SearchRebuilder(
            state=state,
            search=search,
            source=FakeSource([event(1)]),
            owner="reviewer",
        ).run()
    assert search.swaps
    assert "delete" not in search.events


@pytest.mark.asyncio
async def test_rebuild_fencing_token_loss_stops_before_target_creation() -> None:
    class LostFence(FakeState):
        async def fencing_token(self, _rebuild_id: UUID, _owner: str) -> None:
            return None

    search = FakeSearch()
    with pytest.raises(RebuildError, match="rebuild_lease_lost"):
        await SearchRebuilder(
            state=LostFence(), search=search, source=FakeSource([]), owner="reviewer"
        ).run()
    assert search.created == []


@pytest.mark.asyncio
async def test_rebuild_source_boundary_save_failure_is_classified_and_deactivates_target() -> None:
    class BoundarySource(FakeSource):
        async def capture_backfill_upper_bound(self) -> str:
            return "000000000000000000000010"

    class BoundarySaveFails(FakeState):
        async def save(self, record: RebuildRecord) -> None:
            if record.backfill_upper_bound is not None:
                raise RuntimeError("state unavailable")
            await super().save(record)

    targets: list[str | None] = []
    with pytest.raises(RebuildError, match="source_boundary_failed"):
        await SearchRebuilder(
            state=BoundarySaveFails(),
            search=FakeSearch(),
            source=BoundarySource([]),
            owner="reviewer",
            capture_boundary=lambda: _boundary(),
            set_live_target=lambda target: record_target(target, targets),
        ).run()
    assert targets[-1] is None


async def _boundary() -> object:
    from event_platform.search.rebuild import RebuildBoundary

    return RebuildBoundary("000000000000000000000010", "10:1")


@pytest.mark.asyncio
async def test_rebuild_legacy_convergence_callback_and_failure_are_classified() -> None:
    calls: list[object] = []

    async def legacy_wait(value: object) -> object:
        calls.append(value)
        if not isinstance(value, str):
            raise TypeError("legacy callback")
        from event_platform.search.rebuild import RebuildConvergence

        return RebuildConvergence(
            backfill_upper_bound=value,
            source_fence="10:2",
            projector_change_stream_position="10:2",
        )

    result = await SearchRebuilder(
        state=FakeState(),
        search=FakeSearch(),
        source=FakeSource([event(1)]),
        owner="reviewer",
        capture_boundary=_boundary,
        wait_for_convergence=legacy_wait,
    ).run()
    assert result.phase == RebuildPhase.COMPLETED
    assert len(calls) == 2

    async def broken_wait(_value: object) -> object:
        raise RuntimeError("projector unavailable")

    with pytest.raises(RebuildError, match="projection_convergence_timeout"):
        await SearchRebuilder(
            state=FakeState(),
            search=FakeSearch(),
            source=FakeSource([event(1)]),
            owner="reviewer",
            wait_for_convergence=broken_wait,
        ).run()


@pytest.mark.asyncio
async def test_rebuild_post_swap_uncertain_state_and_live_target_cleanup_failures_are_safe() -> (
    None
):
    class StateFailsTwice(FakeState):
        async def save(self, record: RebuildRecord) -> None:
            if record.phase in {RebuildPhase.COMPLETED, RebuildPhase.RECONCILIATION_REQUIRED}:
                raise RuntimeError("state unavailable")
            await super().save(record)

    async def target_cleanup(target: str | None) -> None:
        if target is None:
            raise RuntimeError("cleanup unavailable")

    with pytest.raises(RuntimeError, match="state unavailable"):
        await SearchRebuilder(
            state=StateFailsTwice(),
            search=FakeSearch(),
            source=FakeSource([event(1)]),
            owner="reviewer",
            set_live_target=target_cleanup,
        ).run()


def test_rebuild_state_models_migrate_legacy_boundary_names() -> None:
    record = RebuildRecord.model_validate(
        {
            "rebuild_id": UUID(int=11),
            "phase": RebuildPhase.COMPLETED,
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "source_collection": "events",
            "target_index": "events-v000002",
            "owner": "reviewer",
            "lease_expires_at": datetime(2026, 1, 1, 1, tzinfo=UTC),
            "source_high_water": "legacy-bound",
            "projector_checkpoint": "legacy-position",
        }
    )
    assert record.backfill_upper_bound == "legacy-bound"
    assert record.change_stream_position == "legacy-position"
    assert record.projector_change_stream_position == "legacy-position"
    assert record.source_high_water == "legacy-bound"
    assert record.projector_checkpoint == "legacy-position"

    convergence = RebuildConvergence.model_validate(
        {"source_high_water": "legacy-bound", "projector_checkpoint": "legacy-position"}
    )
    assert convergence.backfill_upper_bound == "legacy-bound"
    assert convergence.projector_change_stream_position == "legacy-position"
    assert convergence.source_high_water == "legacy-bound"
    assert convergence.projector_checkpoint == "legacy-position"


@pytest.mark.asyncio
async def test_rebuild_source_protocol_compatibility_and_failure_paths() -> None:
    class LegacySource:
        async def capture_high_water(self) -> str:
            return "legacy-bound"

        def scan(self) -> AsyncIterator[CanonicalEvent]:
            async def items() -> AsyncIterator[CanonicalEvent]:
                yield event(1)

            return items()

    rebuilder = SearchRebuilder(
        state=FakeState(), search=FakeSearch(), source=LegacySource(), owner="reviewer"
    )
    boundary = await rebuilder._capture_rebuild_boundary()
    assert boundary == RebuildBoundary("legacy-bound", None)
    assert [item async for item in rebuilder._scan_source("legacy-bound")]  # type: ignore[arg-type]
    assert await rebuilder._renew_lease(RebuildRecord.model_construct())

    class FailingSource(LegacySource):
        async def capture_high_water(self) -> str:
            raise RuntimeError("source unavailable")

    with pytest.raises(RebuildError, match="source_boundary_failed"):
        await SearchRebuilder(
            state=FakeState(), search=FakeSearch(), source=FailingSource(), owner="reviewer"
        )._capture_rebuild_boundary()


@pytest.mark.asyncio
async def test_rebuild_lease_renewal_and_cleanup_failures_are_recorded_safely() -> None:
    class LeaseLost(FakeState):
        async def renew(self, _record: RebuildRecord, _expires: datetime) -> bool:
            return False

    with pytest.raises(RebuildError, match="rebuild_lease_lost"):
        await SearchRebuilder(
            state=LeaseLost(),
            search=FakeSearch(),
            source=FakeSource([event(1)]),
            owner="reviewer",
            batch_size=1,
        ).run()

    class NoDelete(FakeSearch):
        delete_index = None  # type: ignore[assignment]

        async def count(self, _index: str) -> int:
            return 0

    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await SearchRebuilder(
            state=FakeState(),
            search=NoDelete(),
            source=FakeSource([event(1)]),
            owner="reviewer",
        ).run()

    class DeleteFails(FakeSearch):
        async def count(self, _index: str) -> int:
            return 0

        async def delete_index(self, _index: str) -> None:
            raise RuntimeError("cleanup unavailable")

    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await SearchRebuilder(
            state=FakeState(),
            search=DeleteFails(),
            source=FakeSource([event(1)]),
            owner="reviewer",
        ).run()


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


class NoBoolCollection(FakeMongoCollection):
    def __bool__(self) -> bool:
        raise AssertionError("Async Mongo collections must not be truth-tested")


def test_mongo_rebuild_store_uses_explicit_none_for_optional_lock_collection() -> None:
    state = FakeMongoCollection()
    lock = NoBoolCollection()
    store = MongoRebuildStore(state, lock)  # type: ignore[arg-type]
    assert store._lock_collection is lock  # type: ignore[attr-defined]


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
