"""Feature 020 deterministic outage, recovery, and safety invariants."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.main import create_app
from event_platform.queue import InProcessQueue
from event_platform.search.projection import (
    ChangeStreamEvent,
    ProjectionCheckpoint,
    ProjectionError,
    SearchProjector,
)
from event_platform.search.projection import RetryPolicy as ProjectionRetryPolicy
from event_platform.search.rebuild import RebuildError, RebuildRecord, SearchRebuilder
from event_platform.search.search import SearchDependencyError, SearchPage, SearchQuery
from event_platform.storage.mongo import EventAlreadyExists, EventQuery, MongoDependencyError
from event_platform.worker import PersistenceWorker, RetryPolicy

pytestmark = pytest.mark.failure
DEFAULT_EVENT_ID = UUID("00000000-0000-0000-0000-000000000020")


def test_unknown_rebuild_error_code_is_bounded() -> None:
    error = RebuildError("password=secret-driver-detail")
    assert error.code == "rebuild_unexpected_failure"
    assert "secret-driver-detail" not in str(error)


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_event(event_id: UUID = DEFAULT_EVENT_ID) -> CanonicalEvent:
    event_input = EventInput.model_validate(
        {
            "event_type": "purchase",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "failure-user",
            "source_url": "https://example.test/failure",
            "metadata": {"fixture": "feature-020"},
        }
    )
    return CanonicalEvent.from_input(
        event_input,
        event_id=event_id,
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


class RecoveringStore:
    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.events: dict[UUID, CanonicalEvent] = {}
        self.calls = 0

    async def insert(self, value: CanonicalEvent) -> None:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise MongoDependencyError("insert_event")
        if value.event_id in self.events:
            raise EventAlreadyExists("insert_event")
        self.events[value.event_id] = value

    async def get_by_id(self, event_id: UUID) -> CanonicalEvent | None:
        return self.events.get(event_id)

    async def query(self, query: EventQuery) -> AsyncIterator[CanonicalEvent]:
        for value in self.events.values():
            if query.event_type is not None and value.event_type != query.event_type:
                continue
            if query.user_id is not None and value.user_id != query.user_id:
                continue
            yield value


class DeleteFailsOnceQueue(InProcessQueue):
    def __init__(self, *, capacity: int, visibility_timeout: float) -> None:
        super().__init__(capacity=capacity, visibility_timeout=visibility_timeout)
        self.fail_delete = True

    async def delete(self, message_id: str, receipt_handle: str) -> None:
        if self.fail_delete:
            self.fail_delete = False
            raise RuntimeError("injected acknowledgement failure")
        await super().delete(message_id, receipt_handle)


@pytest.mark.asyncio
async def test_mongo_outage_retries_without_ack_and_recovers_with_unhealthy_readiness() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=2, clock=clock)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    store = RecoveringStore(failures=1)
    worker = PersistenceWorker(
        queue,
        store,
        retry_policy=RetryPolicy(base_delay=2, max_delay=2, jitter_ratio=0, max_receive_count=2),
    )

    assert not await worker.process_once()
    assert store.events == {}
    assert (await queue.stats()).depth == 1
    assert (await queue.stats()).visible == 0

    app = create_app(ServiceSettings(env="test"))
    mongo_available = [False]
    worker_healthy = [False]
    with TestClient(app) as client:
        app.state.health.set_probe("mongo", lambda: mongo_available[0])
        app.state.health.set_probe("persistence_worker", lambda: worker_healthy[0])
        app.state.health.set_probe("queue", lambda: True)
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "unhealthy"
        assert ready.json()["components"]["mongo"]["state"] == "unhealthy"
        assert ready.json()["components"]["persistence_worker"]["state"] == "unhealthy"
        mongo_available[0] = True
        worker_healthy[0] = True
        recovered_ready = client.get("/health/ready")
        assert recovered_ready.status_code == 200

    clock.advance(2)
    await queue.wake()
    assert await worker.process_once()
    assert store.events == {value.event_id: value}
    assert (await queue.stats()).depth == 0
    assert worker.metrics.inserted == 1


def payload() -> dict[str, object]:
    return {
        "event_type": "pageview",
        "timestamp": "2026-01-02T03:04:05Z",
        "user_id": "queue-user",
        "source_url": "https://example.test/queue",
        "metadata": {"fixture": "feature-020"},
    }


def test_queue_saturation_returns_503_without_false_acceptance() -> None:
    settings = ServiceSettings(env="test", queue_capacity=1, queue_send_timeout=0)
    with TestClient(create_app(settings)) as client:
        first = client.post("/events", json=payload())
        second = client.post("/events", json=payload())

    assert first.status_code == 202
    assert second.status_code == 503
    assert second.headers["content-type"].startswith("application/problem+json")
    assert second.headers["Retry-After"] == "1"
    assert second.json()["status"] == 503


@pytest.mark.asyncio
async def test_post_insert_pre_ack_failure_redelivery_has_one_canonical_record() -> None:
    value = make_event()
    queue = DeleteFailsOnceQueue(capacity=1, visibility_timeout=0)
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    store = RecoveringStore()
    worker = PersistenceWorker(queue, store)

    with pytest.raises(RuntimeError, match="acknowledgement failure"):
        await worker.process_once()
    assert store.events == {value.event_id: value}

    assert await worker.process_once()
    assert store.events == {value.event_id: value}
    assert worker.metrics.duplicates == 1
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_retry_exhaustion_creates_one_dlq_disposition() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=1, clock=clock)
    value = make_event(UUID("00000000-0000-0000-0000-000000000021"))
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    worker = PersistenceWorker(
        queue,
        RecoveringStore(failures=99),
        retry_policy=RetryPolicy(base_delay=1, max_delay=1, jitter_ratio=0, max_receive_count=2),
    )

    assert not await worker.process_once()
    clock.advance(1)
    await queue.wake()
    assert not await worker.process_once()
    entries = await queue.dlq_entries()
    assert len(entries) == 1
    assert entries[0].reason_code == "mongo_dependency"
    assert entries[0].attempts == 2
    assert (await queue.stats()).depth == 0


class OutageWriter:
    def __init__(self) -> None:
        self.calls = 0

    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        del document_id, source, target_index
        self.calls += 1
        raise ProjectionError("elasticsearch_unavailable", transient=True)


class MemoryCheckpoint:
    def __init__(self, value: ProjectionCheckpoint | None = None) -> None:
        self.value = value

    async def load(self, projector: str) -> ProjectionCheckpoint | None:
        del projector
        return self.value

    async def save(self, checkpoint: ProjectionCheckpoint) -> None:
        self.value = checkpoint


class WorkingWriter:
    def __init__(self) -> None:
        self.calls = 0

    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        del document_id, source, target_index
        self.calls += 1


@pytest.mark.asyncio
async def test_es_outage_keeps_canonical_event_and_checkpoint_until_recovery() -> None:
    value = make_event(UUID("00000000-0000-0000-0000-000000000022"))
    queue = InProcessQueue(capacity=1)
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    store = RecoveringStore()
    worker = PersistenceWorker(queue, store)
    assert await worker.process_once()
    assert await store.get_by_id(value.event_id) == value

    checkpoint = MemoryCheckpoint()
    outage = OutageWriter()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=outage,
        retry_policy=ProjectionRetryPolicy(initial_delay=0, max_attempts=1, jitter_ratio=0),
        sleep=_immediate_sleep,
    )
    await projector.start()
    change = ChangeStreamEvent({"token": 22}, value)
    with pytest.raises(ProjectionError, match="elasticsearch_unavailable"):
        await projector.project_change(change)
    assert checkpoint.value is None
    assert outage.calls == 1

    writer = WorkingWriter()
    recovered = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=writer,
        retry_policy=ProjectionRetryPolicy(initial_delay=0, max_attempts=1, jitter_ratio=0),
    )
    assert (await recovered.project_change(change)).state == "running"
    assert checkpoint.value is not None
    assert checkpoint.value.resume_token == {"token": 22}
    assert writer.calls == 1


@pytest.mark.asyncio
async def test_invalid_resume_history_requires_reconciliation_before_source_open() -> None:
    class InvalidCheckpoint:
        async def load(self, projector: str) -> ProjectionCheckpoint:
            del projector
            raise ProjectionError("checkpoint_invalid")

        async def save(self, checkpoint: ProjectionCheckpoint) -> None:
            del checkpoint

    class Source:
        opened = False

        def stream(
            self, *, resume_after: Mapping[str, object] | None = None
        ) -> AsyncIterator[ChangeStreamEvent]:
            self.opened = True
            del resume_after

            async def items() -> AsyncIterator[ChangeStreamEvent]:
                if False:
                    yield ChangeStreamEvent({}, make_event())

            return items()

    source = Source()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=InvalidCheckpoint(),
        writer=WorkingWriter(),
    )
    status = await projector.run_source(source)
    assert status.state == "reconciliation_required"
    assert status.failure_code == "resume_history_invalid"
    assert source.opened is False


class SearchOutage:
    async def search(self, query: SearchQuery, *, request_id: UUID) -> SearchPage:
        del query, request_id
        raise SearchDependencyError("search_unavailable")


def test_search_outage_is_safe_503_while_canonical_path_remains_usable() -> None:
    value = make_event(UUID("00000000-0000-0000-0000-000000000024"))
    store = RecoveringStore()
    store.events[value.event_id] = value
    app = create_app(ServiceSettings(env="test"))
    app.state.event_store = store
    app.state.search_service = SearchOutage()
    with TestClient(app) as client:
        canonical = client.get("/events", params={"user_id": value.user_id})
        response = client.get("/events/search", params={"q": "feature-020"})
    assert canonical.status_code == 200
    assert [item["event_id"] for item in canonical.json()["items"]] == [str(value.event_id)]
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "search_unavailable" not in response.text


class RebuildState:
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


class AliasSafeSearch:
    def __init__(self) -> None:
        self.alias = "events-v000001"
        self.swaps = 0
        self.deleted: list[str] = []

    async def resolve_alias(self, alias: str) -> str | None:
        del alias
        return self.alias

    async def create_index(self, index: str, definition: Mapping[str, object]) -> None:
        del index, definition

    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int:
        del index, documents
        raise RebuildError("bulk_unavailable")

    async def count(self, index: str) -> int:
        del index
        return 0

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
        del alias, old_index, new_index
        self.swaps += 1
        self.alias = "bad-target"

    async def delete_index(self, index: str) -> None:
        self.deleted.append(index)


class UnexpectedSearch(AliasSafeSearch):
    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int:
        del index, documents
        raise RuntimeError("unexpected driver detail")


class OneEventSource:
    def scan(self) -> AsyncIterator[CanonicalEvent]:
        async def items() -> AsyncIterator[CanonicalEvent]:
            yield make_event(UUID("00000000-0000-0000-0000-000000000023"))

        return items()


@pytest.mark.asyncio
async def test_rebuild_failure_never_moves_serving_alias_to_bad_target() -> None:
    state = RebuildState()
    search = AliasSafeSearch()
    rebuilder = SearchRebuilder(
        state=state,
        search=search,
        source=OneEventSource(),
        owner="feature-020",
    )
    with pytest.raises(RebuildError, match="rebuild_verification_failed"):
        await rebuilder.run()
    assert search.alias == "events-v000001"
    assert search.swaps == 0
    assert search.deleted == ["events-v000002"]
    assert state.records[-1].phase.value == "failed"
    assert all(record.phase.value != "completed" for record in state.records)


@pytest.mark.asyncio
async def test_unexpected_rebuild_failure_is_recorded_and_target_is_cleaned() -> None:
    state = RebuildState()
    search = UnexpectedSearch()
    rebuilder = SearchRebuilder(
        state=state,
        search=search,
        source=OneEventSource(),
        owner="feature-020-unexpected",
    )
    with pytest.raises(RuntimeError, match="unexpected driver detail"):
        await rebuilder.run()
    assert search.alias == "events-v000001"
    assert search.deleted == ["events-v000002"]
    assert state.records[-1].phase.value == "failed"
    assert state.records[-1].failures[-1].code == "rebuild_unexpected_failure"


async def _immediate_sleep(_delay: float) -> None:
    return None
