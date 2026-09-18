"""Feature 007 retry, backoff, and DLQ behavior."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.core.logging import JsonLogFormatter
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.queue import InProcessQueue
from event_platform.storage.mongo import EventAlreadyExists, MongoDependencyError
from event_platform.worker import PersistenceWorker, RetryPolicy

pytestmark = pytest.mark.unit
DEFAULT_EVENT_ID = UUID("00000000-0000-0000-0000-000000000007")


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_event(
    event_type: str = "pageview",
    event_id: UUID = DEFAULT_EVENT_ID,
) -> CanonicalEvent:
    value = EventInput.model_validate(
        {
            "event_type": event_type,
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "retry-user",
            "source_url": "https://example.test/retry",
            "metadata": {"source": "feature-007"},
        }
    )
    return CanonicalEvent.from_input(
        value,
        event_id=event_id,
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


class FakeStore:
    def __init__(self, *, transient_failures: int = 0, error: Exception | None = None) -> None:
        self.transient_failures = transient_failures
        self.error = error
        self.events: dict[UUID, CanonicalEvent] = {}

    async def insert(self, value: CanonicalEvent) -> None:
        if self.transient_failures:
            self.transient_failures -= 1
            raise MongoDependencyError("insert_event")
        if self.error is not None:
            raise self.error
        if value.event_id in self.events:
            raise EventAlreadyExists("insert_event")
        self.events[value.event_id] = value

    async def get_by_id(self, event_id: UUID) -> CanonicalEvent | None:
        return self.events.get(event_id)


class LookupFailureStore(FakeStore):
    async def get_by_id(self, event_id: UUID) -> CanonicalEvent | None:
        raise RuntimeError("lookup secret")


@pytest.mark.asyncio
async def test_transient_failure_schedules_bounded_visibility_then_recovers() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=30, clock=clock)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    store = FakeStore(transient_failures=1)
    worker = PersistenceWorker(
        queue,
        store,  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=2, max_delay=8, jitter_ratio=0, max_receive_count=3),
    )

    assert not await worker.process_once()
    assert worker.metrics.retries == 1
    assert (await queue.stats()).visible == 0
    clock.advance(2)
    await queue.wake()
    assert await worker.process_once()
    assert worker.metrics.inserted == 1
    assert store.events[value.event_id] == value


@pytest.mark.asyncio
async def test_retry_schedule_emits_safe_structured_log(caplog: pytest.LogCaptureFixture) -> None:
    queue = InProcessQueue(capacity=1)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id="log-message")
    worker = PersistenceWorker(
        queue,
        FakeStore(transient_failures=1),  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=2, max_delay=2, jitter_ratio=0),
    )

    with caplog.at_level(logging.INFO, logger="event_platform.worker"):
        assert not await worker.process_once()
    record = next(record for record in caplog.records if record.event == "worker.retry_scheduled")
    assert record.message_id == "log-message"
    assert record.event_id == str(value.event_id)
    assert record.attempt == 1
    assert record.reason_code == "mongo_dependency"
    assert record.delay_seconds == 2
    assert "metadata" not in record.getMessage()
    structured = json.loads(JsonLogFormatter().format(record))
    assert structured["event"] == "worker.retry_scheduled"
    assert structured["message_id"] == "log-message"
    assert structured["delay_seconds"] == 2


def test_retry_policy_is_bounded_and_jitter_is_injectable() -> None:
    positive = RetryPolicy(
        base_delay=2,
        max_delay=5,
        jitter_ratio=1,
        jitter=lambda spread: spread,
    )
    negative = RetryPolicy(
        base_delay=2,
        max_delay=5,
        jitter_ratio=1,
        jitter=lambda spread: -spread,
    )
    assert positive.delay_for(1) == 4
    assert positive.delay_for(2) == 5
    assert positive.delay_for(20) == 5
    assert negative.delay_for(1) == 0
    assert 0 <= negative.delay_for(20) <= 5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_delay": 0},
        {"base_delay": -1},
        {"base_delay": 5, "max_delay": 4},
        {"max_delay": 86_401},
        {"jitter_ratio": -0.1},
        {"jitter_ratio": 1.1},
        {"max_receive_count": 0},
        {"max_receive_count": 1_001},
    ],
)
def test_retry_policy_rejects_unbounded_configuration(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RetryPolicy().delay_for(0)


@pytest.mark.asyncio
async def test_invalid_envelope_is_permanently_dead_lettered_without_ghost() -> None:
    queue = InProcessQueue(capacity=1)
    await queue.send({"not": "canonical"}, message_id="invalid-1")
    worker = PersistenceWorker(queue, FakeStore())  # type: ignore[arg-type]

    assert not await worker.process_once()
    stats = await queue.stats()
    assert stats.depth == 0
    assert stats.dlq_depth == 1
    entry = (await queue.dlq_entries())[0]
    assert entry.classification == "permanent"
    assert entry.reason_code == "invalid_envelope"
    assert entry.attempts == 1
    assert "exception" not in repr(entry)


@pytest.mark.asyncio
async def test_invalid_event_id_is_omitted_from_dlq_log(caplog: pytest.LogCaptureFixture) -> None:
    queue = InProcessQueue(capacity=1)
    await queue.send(
        {"event_id": "secret\nnot-a-uuid", "metadata": {"token": "sentinel"}},
        message_id="safe-message",
    )
    worker = PersistenceWorker(queue, FakeStore())  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="event_platform.worker"):
        assert not await worker.process_once()
    record = next(record for record in caplog.records if record.event == "worker.dlq")
    structured = json.loads(JsonLogFormatter().format(record))
    assert "event_id" not in structured
    assert "secret" not in json.dumps(structured)
    assert "sentinel" not in json.dumps(structured)


@pytest.mark.asyncio
async def test_unknown_failure_retries_then_dead_letters_at_limit() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=0, clock=clock)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    worker = PersistenceWorker(
        queue,
        FakeStore(error=RuntimeError("secret driver details")),  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=1, max_delay=2, jitter_ratio=0, max_receive_count=3),
    )

    assert not await worker.process_once()
    clock.advance(1)
    await queue.wake()
    assert not await worker.process_once()
    clock.advance(2)
    await queue.wake()
    assert not await worker.process_once()
    assert worker.metrics.retries == 2
    assert worker.metrics.dlq == 1
    entry = (await queue.dlq_entries())[0]
    assert entry.classification == "unknown"
    assert entry.reason_code == "unknown_failure"
    assert entry.attempts == 3
    assert "secret driver details" not in repr(entry)
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_repeated_transient_failures_exhaust_to_one_dlq_entry() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=0, clock=clock)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    worker = PersistenceWorker(
        queue,
        FakeStore(transient_failures=10),  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=1, max_delay=2, jitter_ratio=0, max_receive_count=3),
    )

    assert not await worker.process_once()
    clock.advance(1)
    await queue.wake()
    assert not await worker.process_once()
    clock.advance(2)
    await queue.wake()
    assert not await worker.process_once()
    assert worker.metrics.retries == 2
    assert worker.metrics.dlq == 1
    assert (await queue.stats()).depth == 0
    entries = await queue.dlq_entries()
    assert len(entries) == 1
    assert entries[0].attempts == 3
    assert entries[0].reason_code == "mongo_dependency"


@pytest.mark.asyncio
async def test_retry_scheduling_does_not_block_an_eligible_delivery() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=2, visibility_timeout=0, clock=clock)
    poison = make_event("poison")
    healthy = make_event("healthy", UUID("00000000-0000-0000-0000-000000000008"))
    await queue.send(poison.model_dump(mode="json"), message_id=str(poison.event_id))
    await queue.send(healthy.model_dump(mode="json"), message_id=str(healthy.event_id))
    store = FakeStore(transient_failures=1)
    worker = PersistenceWorker(
        queue,
        store,  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=60, max_delay=60, jitter_ratio=0),
    )

    assert not await worker.process_once()
    assert await worker.process_once()
    assert worker.metrics.inserted == 1
    assert healthy.event_id in store.events


@pytest.mark.asyncio
async def test_max_receive_one_dead_letters_first_transient_failure() -> None:
    queue = InProcessQueue(capacity=1)
    value = make_event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    worker = PersistenceWorker(
        queue,
        FakeStore(transient_failures=1),  # type: ignore[arg-type]
        retry_policy=RetryPolicy(max_receive_count=1),
    )

    assert not await worker.process_once()
    assert worker.metrics.retries == 0
    assert worker.metrics.dlq == 1
    entry = (await queue.dlq_entries())[0]
    assert entry.attempts == 1
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_conflict_is_permanently_dead_lettered_without_overwrite() -> None:
    original = make_event()
    incoming = make_event("signup")
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, clock=clock)
    await queue.send(incoming.model_dump(mode="json"), message_id=str(original.event_id))
    store = FakeStore()
    store.events[original.event_id] = original
    worker = PersistenceWorker(queue, store)  # type: ignore[arg-type]

    assert not await worker.process_once()
    assert store.events[original.event_id] == original
    entry = (await queue.dlq_entries())[0]
    assert entry.reason_code == "event_conflict"
    assert entry.classification == "permanent"


@pytest.mark.asyncio
async def test_unknown_duplicate_lookup_failure_receives_explicit_retry() -> None:
    value = make_event()
    queue = InProcessQueue(capacity=1)
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    store = LookupFailureStore()
    store.events[value.event_id] = value
    worker = PersistenceWorker(
        queue,
        store,  # type: ignore[arg-type]
        retry_policy=RetryPolicy(base_delay=1, max_delay=1, jitter_ratio=0),
    )

    assert not await worker.process_once()
    assert worker.metrics.processing_errors == 1
    assert worker.metrics.retries == 1
    assert (await queue.stats()).depth == 1


@pytest.mark.asyncio
async def test_failed_dlq_operation_does_not_remove_source() -> None:
    class FailingDLQQueue(InProcessQueue):
        async def dead_letter(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("dlq unavailable")

    queue = FailingDLQQueue(capacity=1)
    await queue.send({"invalid": True}, message_id="keep-source")
    worker = PersistenceWorker(queue, FakeStore())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="dlq unavailable"):
        await worker.process_once()
    assert (await queue.stats()).depth == 1
    assert (await queue.stats()).dlq_depth == 0


@pytest.mark.asyncio
async def test_worker_run_exits_when_queue_is_closed() -> None:
    queue = InProcessQueue(capacity=1)
    await queue.close()
    worker = PersistenceWorker(queue, FakeStore())  # type: ignore[arg-type]

    await asyncio.wait_for(worker.run(asyncio.Event()), timeout=0.1)


@pytest.mark.asyncio
async def test_worker_run_surfaces_consumer_failure_without_losing_source(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingDLQQueue(InProcessQueue):
        async def dead_letter(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("dlq unavailable")

    queue = FailingDLQQueue(capacity=1)
    await queue.send({"invalid": True}, message_id="supervision-source")
    worker = PersistenceWorker(queue, FakeStore())  # type: ignore[arg-type]

    with (
        pytest.raises(RuntimeError, match="dlq unavailable"),
        caplog.at_level(logging.ERROR, logger="event_platform.worker"),
    ):
        await worker.run(asyncio.Event())
    assert any(record.event == "worker.supervision_failure" for record in caplog.records)
    assert (await queue.stats()).depth == 1
