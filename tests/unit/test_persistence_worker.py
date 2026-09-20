"""Persistence worker ack and idempotency behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.queue import InProcessQueue
from event_platform.storage.mongo import EventAlreadyExists, MongoDependencyError
from event_platform.worker import PersistenceWorker, RetryPolicy

pytestmark = pytest.mark.unit


def event(
    event_type: str = "pageview",
    event_id: UUID | None = None,
) -> CanonicalEvent:
    event_id = event_id or UUID("00000000-0000-0000-0000-000000000001")
    input_event = EventInput.model_validate(
        {
            "event_type": event_type,
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "user-1",
            "source_url": "https://example.test/page",
            "metadata": {"source": "test"},
        }
    )
    return CanonicalEvent.from_input(
        input_event,
        event_id=event_id,
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


class FakeStore:
    def __init__(self, existing: CanonicalEvent | None = None) -> None:
        self.events: dict[UUID, CanonicalEvent] = {}
        if existing:
            self.events[existing.event_id] = existing
        self.fail_once = False
        self.active = 0
        self.max_active = 0

    async def insert(self, value: CanonicalEvent) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            if self.fail_once:
                self.fail_once = False
                raise MongoDependencyError("insert_event")
            if value.event_id in self.events:
                raise EventAlreadyExists("insert_event")
            self.events[value.event_id] = value
        finally:
            self.active -= 1

    async def get_by_id(self, event_id: UUID) -> CanonicalEvent | None:
        return self.events.get(event_id)


class SlowStore(FakeStore):
    async def insert(self, value: CanonicalEvent) -> None:
        await asyncio.sleep(0.025)
        await super().insert(value)


@pytest.mark.asyncio
async def test_insert_ack_boundary_and_metrics() -> None:
    queue = InProcessQueue(capacity=1)
    stored = FakeStore()
    await queue.send(event().model_dump(mode="json"), message_id=str(event().event_id))
    worker = PersistenceWorker(queue, stored)  # type: ignore[arg-type]

    assert await worker.process_once()
    assert (await queue.stats()).depth == 0
    assert worker.metrics.inserted == 1


@pytest.mark.asyncio
async def test_slow_persistence_renews_visibility_without_worker_failure() -> None:
    queue = InProcessQueue(capacity=1, visibility_timeout=0.006)
    value = event()
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    stored = SlowStore()
    worker = PersistenceWorker(queue, stored)  # type: ignore[arg-type]

    assert await worker.process_once()
    assert worker.metrics.visibility_renewals >= 1
    assert worker.metrics.ownership_losses == 0


@pytest.mark.asyncio
async def test_same_hash_duplicate_is_acked_without_overwrite() -> None:
    original = event()
    queue = InProcessQueue(capacity=1)
    await queue.send(original.model_dump(mode="json"), message_id=str(original.event_id))
    stored = FakeStore(original)
    worker = PersistenceWorker(queue, stored)  # type: ignore[arg-type]

    assert await worker.process_once()
    assert worker.metrics.duplicates == 1
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_conflicting_duplicate_uses_disposition_hook_and_never_overwrites() -> None:
    original = event()
    incoming = event("signup")
    queue = InProcessQueue(capacity=1)
    await queue.send(incoming.model_dump(mode="json"), message_id=str(original.event_id))
    stored = FakeStore(original)
    conflicts: list[UUID] = []

    async def dispose(_delivery: object, value: CanonicalEvent, existing: CanonicalEvent) -> bool:
        conflicts.append(value.event_id)
        assert existing.payload_hash != value.payload_hash
        return True

    worker = PersistenceWorker(queue, stored, on_conflict=dispose)  # type: ignore[arg-type]
    assert await worker.process_once()
    assert conflicts == [original.event_id]
    assert stored.events[original.event_id].event_type == original.event_type
    assert worker.metrics.conflicts == 1


@pytest.mark.asyncio
async def test_conflict_hook_rejection_dead_letters_without_ack() -> None:
    original = event()
    incoming = event("signup")
    queue = InProcessQueue(capacity=1)
    await queue.send(incoming.model_dump(mode="json"), message_id=str(original.event_id))
    stored = FakeStore(original)

    async def reject(_delivery: object, _value: CanonicalEvent, _existing: CanonicalEvent) -> bool:
        return False

    worker = PersistenceWorker(queue, stored, on_conflict=reject)  # type: ignore[arg-type]
    assert not await worker.process_once()
    assert worker.metrics.conflicts == 1
    assert (await queue.stats()).dlq_depth == 1
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_conflict_hook_failure_is_unknown_and_does_not_leak_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = event()
    incoming = event("signup")
    queue = InProcessQueue(capacity=1)
    await queue.send(incoming.model_dump(mode="json"), message_id=str(original.event_id))
    stored = FakeStore(original)

    async def explode(_delivery: object, _value: CanonicalEvent, _existing: CanonicalEvent) -> bool:
        raise RuntimeError("secret conflict detail")

    worker = PersistenceWorker(queue, stored, on_conflict=explode)  # type: ignore[arg-type]
    with caplog.at_level("INFO", logger="event_platform.worker"):
        assert not await worker.process_once()
    assert worker.metrics.processing_errors == 1
    assert worker.metrics.retries == 1
    assert (await queue.dlq_entries()) == ()
    assert (await queue.stats()).depth == 1
    assert all("secret conflict detail" not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_failure_before_ack_is_safe_on_redelivery() -> None:
    value = event()
    clock_value = [100.0]
    queue = InProcessQueue(capacity=1, visibility_timeout=0, clock=lambda: clock_value[0])
    await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
    stored = FakeStore()
    stored.fail_once = True
    worker = PersistenceWorker(
        queue,
        stored,
        retry_policy=RetryPolicy(base_delay=1, max_delay=1, jitter_ratio=0),
    )  # type: ignore[arg-type]

    assert not await worker.process_once()
    clock_value[0] += 1
    await queue.wake()
    assert await worker.process_once()
    assert worker.metrics.processing_errors == 1
    assert worker.metrics.inserted == 1


@pytest.mark.asyncio
async def test_run_bounds_concurrency() -> None:
    queue = InProcessQueue(capacity=4)
    stored = FakeStore()
    for index in range(4):
        value = event(event_id=UUID(f"00000000-0000-0000-0000-{index + 1:012d}"))
        await queue.send(value.model_dump(mode="json"), message_id=f"event-{index}")
    stop = asyncio.Event()
    worker = PersistenceWorker(queue, stored, concurrency=2)  # type: ignore[arg-type]
    task = asyncio.create_task(worker.run(stop))
    for _ in range(100):
        if worker.metrics.inserted >= 4:
            break
        if task.done():
            await task
            break
        await asyncio.sleep(0)
    else:
        stop.set()
        await task
        pytest.fail("worker did not process the queued messages within the scheduling bound")
    stop.set()
    await task
    assert stored.max_active <= 2
    with pytest.raises(ValueError):
        PersistenceWorker(queue, stored, concurrency=0)  # type: ignore[arg-type]
