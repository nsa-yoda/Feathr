from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest
from elastic_transport import TransportError
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.projection import (
    ChangeStreamEvent,
    InvalidResumeHistory,
    ProjectionCheckpoint,
    ProjectionError,
    RetryPolicy,
    SearchProjector,
    project_event,
)
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import (
    CheckpointDependencyError,
    MongoProjectionCheckpointStore,
)
from event_platform.storage.mongo import event_to_document

pytestmark = pytest.mark.unit


def make_event() -> CanonicalEvent:
    event_input = EventInput.model_validate(
        {
            "event_type": "pageview",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "user-1",
            "source_url": "https://example.test/page",
            "metadata": {"campaign": "winter", "rank": 2},
        }
    )
    return CanonicalEvent.from_input(
        event_input,
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


class FakeCheckpoint:
    def __init__(
        self,
        initial: ProjectionCheckpoint | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.current = initial
        self.saved: list[ProjectionCheckpoint] = []
        self.calls = calls if calls is not None else []
        self.fail = False

    async def load(self, projector: str) -> ProjectionCheckpoint | None:
        self.calls.append("load")
        return self.current

    async def save(self, checkpoint: ProjectionCheckpoint) -> None:
        self.calls.append("checkpoint")
        if self.fail:
            raise ProjectionError("checkpoint_unavailable", transient=True)
        self.current = checkpoint
        self.saved.append(checkpoint)


class FakeWriter:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.documents: list[tuple[str, Mapping[str, object], str | None]] = []
        self.error: ProjectionError | None = None
        self.fail_target = False

    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        self.calls.append("es")
        if self.error is not None:
            raise self.error
        if target_index is not None and self.fail_target:
            raise ProjectionError("elasticsearch_unavailable", transient=True)
        self.documents.append((document_id, source, target_index))


def change(token: Mapping[str, object] | None = None) -> ChangeStreamEvent:
    return ChangeStreamEvent(token or {"_data": "resume-1"}, make_event())


@pytest.mark.asyncio
async def test_projection_is_deterministic_and_checkpoint_follows_all_writes() -> None:
    event = make_event()
    first = project_event(event)
    second = project_event(event)
    assert first == second
    assert first["event_id"] == str(event.event_id)
    assert first["metadata"] == {"campaign": "winter", "rank": 2}
    assert first["metadata_text"] == "campaign winter rank 2"

    calls: list[str] = []
    writer = FakeWriter(calls)
    checkpoint = FakeCheckpoint(calls=calls)
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=writer,
        target_index="events-v2",
    )
    await projector.start()
    status = await projector.project_change(change())
    assert calls == ["load", "es", "checkpoint"]
    assert writer.documents == [(str(event.event_id), first, "events-v2")]
    assert status.checkpoint_present is True
    assert status.state == "running"


@pytest.mark.asyncio
async def test_projector_uses_explicit_owner_generation_and_bounded_batches() -> None:
    calls: list[str] = []
    checkpoint = FakeCheckpoint(calls=calls)
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=FakeWriter(calls),
        owner="pod-a",
        generation=3,
    )
    await projector.start()
    await projector.project_batch([change(), change({"_data": "resume-2"})])
    assert checkpoint.current is not None
    assert checkpoint.current.owner == "pod-a"
    assert checkpoint.current.generation == 3
    with pytest.raises(ValueError):
        await projector.project_batch([change()] * 1001)


@pytest.mark.asyncio
async def test_replay_uses_same_document_id_and_checkpoint_is_not_advanced_on_es_failure() -> None:
    writer = FakeWriter([])
    checkpoint = FakeCheckpoint()
    projector = SearchProjector(projector="events-search", checkpoint=checkpoint, writer=writer)
    await projector.start()
    await projector.project_change(change())
    writer.error = ProjectionError("elasticsearch_unavailable", transient=True)
    with pytest.raises(ProjectionError):
        await projector.project_change(change({"_data": "resume-2"}))
    assert len(writer.documents) == 1
    assert checkpoint.current is not None
    assert checkpoint.current.resume_token == {"_data": "resume-1"}
    assert projector.status().state == "retrying"

    writer.error = None
    for index in range(100):
        await projector.project_change(change({"_data": f"replay-{index}"}))
    assert {document_id for document_id, _, _ in writer.documents} == {str(make_event().event_id)}


@pytest.mark.asyncio
async def test_target_write_failure_retains_checkpoint() -> None:
    writer = FakeWriter([])
    checkpoint = FakeCheckpoint()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=writer,
        target_index="events-v2",
    )
    await projector.start()
    writer.fail_target = True
    with pytest.raises(ProjectionError):
        await projector.project_change(change())
    assert checkpoint.current is None
    assert projector.status().state == "retrying"


@pytest.mark.asyncio
async def test_run_retries_to_recovery_or_bounded_exhaustion() -> None:
    class FlakyWriter(FakeWriter):
        def __init__(self, remaining: int) -> None:
            super().__init__([])
            self.remaining = remaining

        async def write(
            self,
            document_id: str,
            source: Mapping[str, object],
            *,
            target_index: str | None = None,
        ) -> None:
            if self.remaining:
                self.remaining -= 1
                raise ProjectionError("elasticsearch_unavailable", transient=True)
            await super().write(document_id, source, target_index=target_index)

    async def one_change() -> AsyncIterator[ChangeStreamEvent]:
        yield change()

    recovered_writer = FlakyWriter(2)
    recovered_checkpoint = FakeCheckpoint()
    recovered = SearchProjector(
        projector="events-search",
        checkpoint=recovered_checkpoint,
        writer=recovered_writer,
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=3),
        sleep=lambda _delay: _instant_sleep(),
    )
    assert (await recovered.run(one_change())).state == "running"
    assert recovered_checkpoint.current is not None

    exhausted_checkpoint = FakeCheckpoint()
    exhausted = SearchProjector(
        projector="events-search",
        checkpoint=exhausted_checkpoint,
        writer=FlakyWriter(9),
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2),
        sleep=lambda _delay: _instant_sleep(),
    )
    assert (await exhausted.run(one_change())).state == "degraded"
    assert exhausted.status().failure_code == "retry_exhausted"
    assert exhausted_checkpoint.current is None


async def _instant_sleep() -> None:
    return None


@pytest.mark.asyncio
async def test_retry_policy_is_bounded_and_injected_sleep_is_used() -> None:
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    writer = FakeWriter([])
    writer.error = ProjectionError("elasticsearch_unavailable", transient=True)
    projector = SearchProjector(
        projector="events-search",
        checkpoint=FakeCheckpoint(),
        writer=writer,
        retry_policy=RetryPolicy(initial_delay=2, max_delay=3, jitter_ratio=0, max_attempts=2),
        sleep=sleep,
    )
    await projector.start()
    with pytest.raises(ProjectionError):
        await projector.retry_change(change(), 1)
    assert waits == [2]


@pytest.mark.asyncio
async def test_invalid_resume_and_stop_are_visible_without_token_leakage() -> None:
    projector = SearchProjector(
        projector="events-search", checkpoint=FakeCheckpoint(), writer=FakeWriter([])
    )
    await projector.start()
    status = projector.mark_reconciliation_required()
    assert status.state == "reconciliation_required"
    assert status.failure_code == "resume_history_invalid"
    assert "resume-1" not in repr(status)
    assert projector.stop().state == "stopped"


@pytest.mark.asyncio
async def test_run_marks_invalid_stream_history_without_consuming_new_events() -> None:
    async def stream() -> AsyncIterator[ChangeStreamEvent]:
        raise InvalidResumeHistory()
        yield

    projector = SearchProjector(
        projector="events-search", checkpoint=FakeCheckpoint(), writer=FakeWriter([])
    )
    status = await projector.run(stream())
    assert status.state == "reconciliation_required"
    assert status.failure_code == "resume_history_invalid"


@pytest.mark.asyncio
async def test_run_source_resumes_from_checkpoint_token() -> None:
    checkpoint = FakeCheckpoint(
        ProjectionCheckpoint(
            projector="events-search",
            resume_token={"_data": "resume-previous"},
            updated_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        )
    )

    class Source:
        def __init__(self) -> None:
            self.resume_after: Mapping[str, object] | None = None

        def stream(
            self, *, resume_after: Mapping[str, object] | None = None
        ) -> AsyncIterator[ChangeStreamEvent]:
            self.resume_after = resume_after

            async def items() -> AsyncIterator[ChangeStreamEvent]:
                if False:
                    yield change()

            return items()

    source = Source()
    projector = SearchProjector(
        projector="events-search", checkpoint=checkpoint, writer=FakeWriter([])
    )
    status = await projector.run_source(source)
    assert status.state == "running"
    assert source.resume_after == {"_data": "resume-previous"}


@pytest.mark.asyncio
async def test_reconnect_uses_latest_successful_checkpoint_token() -> None:
    class Source:
        def __init__(self) -> None:
            self.calls: list[Mapping[str, object] | None] = []

        def stream(
            self, *, resume_after: Mapping[str, object] | None = None
        ) -> AsyncIterator[ChangeStreamEvent]:
            self.calls.append(resume_after)

            async def items() -> AsyncIterator[ChangeStreamEvent]:
                if len(self.calls) == 1:
                    yield change({"_data": "latest"})
                    raise ProjectionError("dependency_unavailable", transient=True)

            return items()

    source = Source()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=FakeCheckpoint(),
        writer=FakeWriter([]),
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2),
        sleep=lambda _delay: _instant_sleep(),
    )
    await projector.run_source(source)
    assert source.calls == [None, {"_data": "latest"}]


@pytest.mark.asyncio
async def test_shutdown_and_cancellation_preserve_last_checkpoint() -> None:
    release = asyncio.Event()

    async def controlled_stream() -> AsyncIterator[ChangeStreamEvent]:
        yield change()
        await release.wait()

    checkpoint = FakeCheckpoint()
    writer = FakeWriter([])
    projector = SearchProjector(projector="events-search", checkpoint=checkpoint, writer=writer)
    task = asyncio.create_task(projector.run(controlled_stream()))
    for _ in range(100):
        if checkpoint.current is not None:
            break
        await asyncio.sleep(0)
    projector.stop()
    release.set()
    assert (await task).state == "stopped"
    assert checkpoint.current is not None

    waiting = asyncio.Event()

    async def waiting_stream() -> AsyncIterator[ChangeStreamEvent]:
        await waiting.wait()
        yield change()

    restarted = SearchProjector(
        projector="events-search", checkpoint=checkpoint, writer=FakeWriter([])
    )
    cancelled = asyncio.create_task(restarted.run(waiting_stream()))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert checkpoint.current is not None


@pytest.mark.asyncio
async def test_shutdown_during_startup_does_not_open_consumption() -> None:
    loading = asyncio.Event()
    release = asyncio.Event()
    opened = False

    class BlockingCheckpoint(FakeCheckpoint):
        async def load(self, projector: str) -> ProjectionCheckpoint | None:
            del projector
            loading.set()
            await release.wait()
            return None

    async def stream() -> AsyncIterator[ChangeStreamEvent]:
        nonlocal opened
        opened = True
        yield change()

    projector = SearchProjector(
        projector="events-search", checkpoint=BlockingCheckpoint(), writer=FakeWriter([])
    )
    task = asyncio.create_task(projector.run(stream()))
    await loading.wait()
    assert projector.stop().state == "stopped"
    release.set()

    status = await task
    assert status.state == "stopped"
    assert opened is False


@pytest.mark.asyncio
async def test_checkpoint_retry_exhaustion_preserves_known_progress() -> None:
    checkpoint = ProjectionCheckpoint(
        projector="events-search",
        resume_token={"_data": "known"},
        updated_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        last_projected_event_at=make_event().timestamp,
    )

    class FailingCheckpoint(FakeCheckpoint):
        def __init__(self) -> None:
            super().__init__(initial=checkpoint)
            self.fail_load = False

        async def load(self, projector: str) -> ProjectionCheckpoint | None:
            del projector
            if self.fail_load:
                raise ProjectionError("checkpoint_unavailable", transient=True)
            return self.current

    class UnopenedSource:
        def stream(self, *, resume_after: Mapping[str, object] | None = None):
            raise AssertionError(f"stream opened unexpectedly: {resume_after}")

    failing_checkpoint = FailingCheckpoint()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=failing_checkpoint,
        writer=FakeWriter([]),
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=1),
        sleep=lambda _delay: _instant_sleep(),
    )
    await projector.start()
    failing_checkpoint.fail_load = True
    status = await projector.run_source(UnopenedSource())

    assert status.state == "degraded"
    assert status.failure_code == "retry_exhausted"
    assert status.checkpoint_present is True
    assert status.last_projected_event_at == checkpoint.last_projected_event_at


@pytest.mark.asyncio
async def test_status_lag_and_state_transition_logs_are_safe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime(2026, 1, 2, 5, 4, 5, tzinfo=UTC)
    projector = SearchProjector(
        projector="events-search",
        checkpoint=FakeCheckpoint(),
        writer=FakeWriter([]),
        now=lambda: now,
    )
    with caplog.at_level(logging.INFO, logger="event_platform.search_projection"):
        await projector.start()
        status = await projector.project_change(change())
        projector.stop()
    assert status.last_success_at == now
    assert status.last_projected_event_at == make_event().timestamp
    assert status.lag_seconds == pytest.approx(7200)
    assert {record.event for record in caplog.records} >= {
        "projector.start",
        "projector.success",
        "projector.shutdown",
    }
    assert all("resume-1" not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_retry_and_reconciliation_logs_are_safe(caplog: pytest.LogCaptureFixture) -> None:
    writer = FakeWriter([])
    writer.error = ProjectionError("elasticsearch_unavailable", transient=True)
    projector = SearchProjector(
        projector="events-search",
        checkpoint=FakeCheckpoint(),
        writer=writer,
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=1),
        sleep=lambda _delay: _instant_sleep(),
    )
    with caplog.at_level(logging.INFO, logger="event_platform.search_projection"):
        await projector.start()
        with pytest.raises(ProjectionError):
            await projector.retry_change(change(), 1)
        projector.mark_reconciliation_required()
    events = {record.event for record in caplog.records}
    assert {"projector.retry_scheduled", "projector.reconciliation_required"} <= events
    assert all("resume-1" not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_missing_checkpoint_starts_stream_without_fabricated_progress() -> None:
    class Source:
        def __init__(self) -> None:
            self.resume_after: Mapping[str, object] | None = None

        def stream(
            self, *, resume_after: Mapping[str, object] | None = None
        ) -> AsyncIterator[ChangeStreamEvent]:
            self.resume_after = resume_after

            async def items() -> AsyncIterator[ChangeStreamEvent]:
                if False:
                    yield change()

            return items()

    source = Source()
    projector = SearchProjector(
        projector="events-search", checkpoint=FakeCheckpoint(), writer=FakeWriter([])
    )
    status = await projector.run_source(source)
    assert source.resume_after is None
    assert status.checkpoint_present is False
    assert status.last_success_at is None
    assert status.lag_seconds is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["event_id", "timestamp", "event_type", "user_id"])
async def test_malformed_canonical_fields_are_rejected(missing: str) -> None:
    document = event_to_document(make_event())
    document.pop(missing)
    collection = StreamCollection(
        FakeStream(
            [
                {
                    "_id": {"x": 1},
                    "operationType": "insert",
                    "fullDocument": document,
                }
            ]
        )
    )
    with pytest.raises(ProjectionError, match="change_malformed"):
        [item async for item in MongoChangeStreamSource(collection).stream()]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_invalid_checkpoint_prevents_opening_a_new_stream() -> None:
    class InvalidCheckpoint:
        async def load(self, projector: str) -> None:
            del projector
            raise ProjectionError("checkpoint_invalid")

    class Source:
        opened = False

        def stream(
            self, *, resume_after: Mapping[str, object] | None = None
        ) -> AsyncIterator[ChangeStreamEvent]:
            del resume_after
            self.opened = True

            async def empty() -> AsyncIterator[ChangeStreamEvent]:
                if False:
                    yield change()

            return empty()

    source = Source()
    projector = SearchProjector(
        projector="events-search", checkpoint=InvalidCheckpoint(), writer=FakeWriter([])
    )
    assert (await projector.run_source(source)).state == "reconciliation_required"
    assert source.opened is False


@pytest.mark.asyncio
async def test_malformed_stream_degrades_without_advancing_checkpoint() -> None:
    checkpoint = FakeCheckpoint()
    writer = FakeWriter([])
    projector = SearchProjector(projector="events-search", checkpoint=checkpoint, writer=writer)
    await projector.start()
    await projector.project_change(change({"_data": "good"}))

    async def malformed_source() -> AsyncIterator[ChangeStreamEvent]:
        raise ProjectionError("change_malformed")
        yield change()

    status = await projector.run(malformed_source())
    assert status.state == "degraded"
    assert status.failure_code == "change_malformed"
    assert checkpoint.current is not None
    assert checkpoint.current.resume_token == {"_data": "good"}
    assert len(writer.documents) == 1


class FakeCollection:
    def __init__(self, document: Mapping[str, object] | None = None) -> None:
        self.document = document
        self.saved: Mapping[str, object] | None = None
        self.error: Exception | None = None

    async def find_one(self, query: Mapping[str, object]) -> Mapping[str, object] | None:
        del query
        if self.error:
            raise self.error
        return self.document

    async def replace_one(
        self,
        query: Mapping[str, object],
        document: Mapping[str, object],
        *,
        upsert: bool,
    ) -> None:
        del query, upsert
        if self.error:
            raise self.error
        self.saved = document


@pytest.mark.asyncio
async def test_checkpoint_store_round_trip_and_invalid_token() -> None:
    collection = FakeCollection()
    store = MongoProjectionCheckpointStore(collection)  # type: ignore[arg-type]
    checkpoint = ProjectionCheckpoint(
        projector="events-search",
        resume_token={"_data": "abc"},
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await store.save(checkpoint)
    collection.document = collection.saved
    loaded = await store.load("events-search")
    assert loaded is not None
    assert loaded.resume_token == {"_data": "abc"}

    collection.document = {"projector": "events-search", "resume_token": "not-a-map"}
    with pytest.raises(ProjectionError, match="checkpoint_invalid"):
        await store.load("events-search")

    with pytest.raises(ProjectionError, match="checkpoint_invalid"):
        await store.save(
            ProjectionCheckpoint(
                projector="events-search",
                resume_token={"bad": object()},
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


@pytest.mark.asyncio
async def test_checkpoint_store_translates_driver_failures_to_safe_dependency_errors() -> None:
    collection = FakeCollection()
    collection.error = PyMongoError("driver unavailable")
    store = MongoProjectionCheckpointStore(collection)  # type: ignore[arg-type]

    with pytest.raises(CheckpointDependencyError, match="checkpoint_unavailable"):
        await store.load("events-search")

    with pytest.raises(CheckpointDependencyError, match="checkpoint_unavailable"):
        await store.save(
            ProjectionCheckpoint(
                projector="events-search",
                resume_token={"_data": "abc"},
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )


class FakeStream:
    def __init__(self, changes: list[Mapping[str, object]]) -> None:
        self.changes = changes

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> Mapping[str, object]:
        if not self.changes:
            raise StopAsyncIteration
        return self.changes.pop(0)


class StreamCollection:
    def __init__(self, stream: FakeStream) -> None:
        self.stream_value = stream
        self.kwargs: dict[str, object] = {}

    async def watch(self, pipeline: object, **kwargs: object) -> FakeStream:
        self.kwargs = {"pipeline": pipeline, **kwargs}
        return self.stream_value


@pytest.mark.asyncio
async def test_change_stream_filters_inserts_and_decodes_canonical_event() -> None:
    event = make_event()
    document = {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "user_id": event.user_id,
        "source_url": str(event.source_url),
        "metadata": {"campaign": "winter", "rank": 2},
        "ingested_at": event.ingested_at,
        "schema_version": 1,
        "payload_hash": event.payload_hash,
        "idempotency_key_hash": None,
    }
    collection = StreamCollection(
        FakeStream([{"_id": {"x": 1}, "operationType": "insert", "fullDocument": document}])
    )
    source = MongoChangeStreamSource(collection)  # type: ignore[arg-type]
    items = [item async for item in source.stream(resume_after={"old": 1})]
    assert len(items) == 1
    assert items[0].event.event_id == event.event_id
    assert collection.kwargs["resume_after"] == {"old": 1}
    assert collection.kwargs["pipeline"] == [{"$match": {"operationType": "insert"}}]


@pytest.mark.asyncio
async def test_change_stream_rejects_malformed_changes_and_invalid_history() -> None:
    malformed = StreamCollection(FakeStream([{"_id": {"x": 1}}]))
    with pytest.raises(ProjectionError, match="change_malformed"):
        [item async for item in MongoChangeStreamSource(malformed).stream()]  # type: ignore[arg-type]

    update = StreamCollection(
        FakeStream([{"_id": {"x": 1}, "operationType": "update", "fullDocument": {}}])
    )
    with pytest.raises(ProjectionError, match="change_malformed"):
        [item async for item in MongoChangeStreamSource(update).stream()]  # type: ignore[arg-type]

    class InvalidCollection(StreamCollection):
        async def watch(self, pipeline: object, **kwargs: object) -> FakeStream:
            del pipeline, kwargs
            raise PyMongoError("resume history is no longer available")

    with pytest.raises(ProjectionError, match="resume_history_invalid"):
        [
            item
            async for item in MongoChangeStreamSource(InvalidCollection(FakeStream([]))).stream(
                resume_after={"old": 1}
            )
        ]  # type: ignore[arg-type]

    class DownCollection(StreamCollection):
        async def watch(self, pipeline: object, **kwargs: object) -> FakeStream:
            del pipeline, kwargs
            raise PyMongoError("mongo unavailable")

    with pytest.raises(ProjectionError, match="dependency_unavailable"):
        [item async for item in MongoChangeStreamSource(DownCollection(FakeStream([]))).stream()]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_elasticsearch_writer_writes_alias_then_target_and_translates_outage() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.error = False

        async def index(self, **kwargs: object) -> None:
            if self.error:
                raise PyMongoError("wrong fake")
            self.calls.append(kwargs)

        async def close(self) -> None:
            return None

    client = Client()
    writer = ElasticsearchProjectionWriter(client, alias="events-search")  # type: ignore[arg-type]
    await writer.write("event-1", {"event_id": "event-1"}, target_index="events-v2")
    assert [call["index"] for call in client.calls] == ["events-search", "events-v2"]

    class DownClient(Client):
        async def index(self, **kwargs: object) -> None:
            del kwargs
            raise TransportError("down", ())

    with pytest.raises(ProjectionError, match="elasticsearch_unavailable"):
        await ElasticsearchProjectionWriter(DownClient(), alias="events-search").write(
            "event-1", {"event_id": "event-1"}
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_elasticsearch_writer_bulk_path_reports_partial_failures() -> None:
    class BulkClient:
        def __init__(self, errors: bool = False) -> None:
            self.errors = errors
            self.operations: list[object] = []

        async def bulk(self, **kwargs: object) -> dict[str, object]:
            self.operations = list(kwargs["operations"])  # type: ignore[arg-type]
            return {"errors": self.errors}

    client = BulkClient()
    writer = ElasticsearchProjectionWriter(client, alias="events-search")  # type: ignore[arg-type]
    await writer.bulk_write(
        [("one", {"event_id": "one"}), ("two", {"event_id": "two"})],
        target_index="events-v2",
    )
    assert len(client.operations) == 8
    with pytest.raises(ProjectionError, match="elasticsearch_unavailable"):
        await ElasticsearchProjectionWriter(BulkClient(True), alias="events-search").bulk_write(
            [("one", {"event_id": "one"})]
        )  # type: ignore[arg-type]
