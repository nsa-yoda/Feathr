"""Ack-after-persist worker for canonical event deliveries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError

from event_platform.domain.events import CanonicalEvent
from event_platform.queue import Delivery, InProcessQueue, QueueClosed
from event_platform.storage.mongo import (
    EventAlreadyExists,
    MongoDependencyError,
    MongoEventStore,
)


@dataclass(frozen=True, slots=True)
class WorkerMetrics:
    inserted: int = 0
    duplicates: int = 0
    conflicts: int = 0
    decode_failures: int = 0
    processing_errors: int = 0


ConflictDisposition = Callable[[Delivery, CanonicalEvent, CanonicalEvent], Awaitable[bool]]


class PersistenceWorker:
    """Consume queue envelopes and acknowledge only after canonical persistence."""

    def __init__(
        self,
        queue: InProcessQueue,
        store: MongoEventStore,
        *,
        concurrency: int = 1,
        on_conflict: ConflictDisposition | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self._queue = queue
        self._store = store
        self._concurrency = concurrency
        self._on_conflict = on_conflict
        self._metrics = WorkerMetrics()

    @property
    def metrics(self) -> WorkerMetrics:
        return self._metrics

    async def process_once(self, *, long_poll: float = 0.0) -> bool:
        try:
            delivery = await self._queue.receive(long_poll=long_poll)
        except TimeoutError:
            return False
        except QueueClosed:
            return False

        try:
            event = CanonicalEvent.model_validate(delivery.body)
        except ValidationError:
            self._metrics = _increment(self._metrics, "decode_failures")
            return False

        try:
            await self._store.insert(event)
        except EventAlreadyExists:
            existing = await self._store.get_by_id(event.event_id)
            if existing is None:
                self._metrics = _increment(self._metrics, "processing_errors")
                return False
            if existing.payload_hash == event.payload_hash:
                await self._queue.delete(delivery.message_id, delivery.receipt_handle)
                self._metrics = _increment(self._metrics, "duplicates")
                return True
            self._metrics = _increment(self._metrics, "conflicts")
            if self._on_conflict is not None and await self._on_conflict(delivery, event, existing):
                await self._queue.delete(delivery.message_id, delivery.receipt_handle)
                return True
            return False
        except MongoDependencyError:
            self._metrics = _increment(self._metrics, "processing_errors")
            return False

        await self._queue.delete(delivery.message_id, delivery.receipt_handle)
        self._metrics = _increment(self._metrics, "inserted")
        return True

    async def run(self, stop_event: asyncio.Event) -> None:
        async def consume() -> None:
            while not stop_event.is_set():
                await self.process_once(long_poll=1.0)

        tasks = [asyncio.create_task(consume()) for _ in range(self._concurrency)]
        await stop_event.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _increment(metrics: WorkerMetrics, field: str) -> WorkerMetrics:
    values = {
        "inserted": metrics.inserted,
        "duplicates": metrics.duplicates,
        "conflicts": metrics.conflicts,
        "decode_failures": metrics.decode_failures,
        "processing_errors": metrics.processing_errors,
    }
    values[field] += 1
    return WorkerMetrics(**values)
