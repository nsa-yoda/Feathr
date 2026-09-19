"""Ack-after-persist worker for canonical event deliveries."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from math import isfinite
from random import uniform
from uuid import UUID

from pydantic import ValidationError

from event_platform.domain.events import CanonicalEvent
from event_platform.queue import (
    Delivery,
    DLQClassification,
    DLQReasonCode,
    InProcessQueue,
    QueueClosed,
)
from event_platform.storage.mongo import (
    EventAlreadyExists,
    MongoDependencyError,
    MongoEventStore,
)

logger = logging.getLogger("event_platform.worker")


@dataclass(frozen=True, slots=True)
class WorkerMetrics:
    inserted: int = 0
    duplicates: int = 0
    conflicts: int = 0
    decode_failures: int = 0
    processing_errors: int = 0
    retries: int = 0
    dlq: int = 0


ConflictDisposition = Callable[[Delivery, CanonicalEvent, CanonicalEvent], Awaitable[bool]]
FailureClassification = DLQClassification


def _random_jitter(spread: float) -> float:
    return uniform(-spread, spread)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded visibility delay policy with injectable jitter."""

    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_ratio: float = 0.2
    max_receive_count: int = 5
    jitter: Callable[[float], float] = _random_jitter

    def __post_init__(self) -> None:
        if not all(
            isfinite(value) for value in (self.base_delay, self.max_delay, self.jitter_ratio)
        ):
            raise ValueError("retry delay settings must be finite")
        if not 0 < self.base_delay <= self.max_delay <= 86_400:
            raise ValueError("retry delays must satisfy 0 < base <= cap <= 86400")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if not 1 <= self.max_receive_count <= 1_000:
            raise ValueError("max_receive_count must be between 1 and 1000")

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be positive")
        exponent = min(attempt - 1, 30)
        base = min(self.max_delay, self.base_delay * (2.0**exponent))
        spread = base * self.jitter_ratio
        adjustment = self.jitter(spread)
        if not isfinite(adjustment):
            raise ValueError("jitter result must be finite")
        return max(0.0, min(self.max_delay, base + adjustment))


def classify_failure(error: Exception) -> tuple[FailureClassification, DLQReasonCode]:
    """Map known worker errors to bounded, safe operational reason codes."""

    if isinstance(error, MongoDependencyError):
        return "transient", "mongo_dependency"
    if isinstance(error, ValidationError):
        return "permanent", "invalid_envelope"
    if isinstance(error, EventAlreadyExists):
        return "permanent", "event_conflict"
    return "unknown", "unknown_failure"


class PersistenceWorker:
    """Consume queue envelopes and acknowledge only after canonical persistence."""

    def __init__(
        self,
        queue: InProcessQueue,
        store: MongoEventStore,
        *,
        concurrency: int = 1,
        on_conflict: ConflictDisposition | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        self._queue = queue
        self._store = store
        self._concurrency = concurrency
        self._on_conflict = on_conflict
        self._retry_policy = retry_policy or RetryPolicy()
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
            return await self._dispose_failure(
                delivery, classification="permanent", reason_code="invalid_envelope"
            )

        try:
            await self._store.insert(event)
        except EventAlreadyExists:
            try:
                existing = await self._store.get_by_id(event.event_id)
            except MongoDependencyError:
                self._metrics = _increment(self._metrics, "processing_errors")
                return await self._dispose_failure(
                    delivery, classification="transient", reason_code="mongo_dependency"
                )
            except Exception as error:
                self._metrics = _increment(self._metrics, "processing_errors")
                classification, reason_code = classify_failure(error)
                return await self._dispose_failure(
                    delivery, classification=classification, reason_code=reason_code
                )
            if existing is None:
                self._metrics = _increment(self._metrics, "processing_errors")
                return await self._dispose_failure(
                    delivery, classification="transient", reason_code="mongo_dependency"
                )
            if existing.payload_hash == event.payload_hash:
                await self._queue.delete(delivery.message_id, delivery.receipt_handle)
                self._metrics = _increment(self._metrics, "duplicates")
                return True
            self._metrics = _increment(self._metrics, "conflicts")
            if self._on_conflict is not None:
                try:
                    accepted = await self._on_conflict(delivery, event, existing)
                except Exception:
                    self._metrics = _increment(self._metrics, "processing_errors")
                    return await self._dispose_failure(
                        delivery, classification="unknown", reason_code="unknown_failure"
                    )
                if accepted:
                    await self._queue.delete(delivery.message_id, delivery.receipt_handle)
                    return True
            return await self._dispose_failure(
                delivery, classification="permanent", reason_code="event_conflict"
            )
        except MongoDependencyError:
            self._metrics = _increment(self._metrics, "processing_errors")
            return await self._dispose_failure(
                delivery, classification="transient", reason_code="mongo_dependency"
            )
        except Exception as error:
            self._metrics = _increment(self._metrics, "processing_errors")
            classification, reason_code = classify_failure(error)
            return await self._dispose_failure(
                delivery, classification=classification, reason_code=reason_code
            )

        await self._queue.delete(delivery.message_id, delivery.receipt_handle)
        self._metrics = _increment(self._metrics, "inserted")
        return True

    async def _dispose_failure(
        self,
        delivery: Delivery,
        *,
        classification: FailureClassification,
        reason_code: DLQReasonCode,
    ) -> bool:
        event_id = delivery.body.get("event_id")
        safe_event_id: str | None = None
        if isinstance(event_id, str):
            try:
                safe_event_id = str(UUID(event_id))
            except ValueError:
                pass
        if (
            classification == "permanent"
            or delivery.receive_count >= self._retry_policy.max_receive_count
        ):
            await self._queue.dead_letter(
                delivery.message_id,
                delivery.receipt_handle,
                classification=classification,
                reason_code=reason_code,
            )
            self._metrics = _increment(self._metrics, "dlq")
            logger.warning(
                "worker delivery moved to dead letter queue",
                extra={
                    "event": "worker.dlq",
                    "message_id": delivery.message_id,
                    "event_id": safe_event_id,
                    "operation_id": delivery.operation_id,
                    "attempt": delivery.receive_count,
                    "classification": classification,
                    "reason_code": reason_code,
                },
            )
            return False

        delay = self._retry_policy.delay_for(delivery.receive_count)
        await self._queue.change_visibility(
            delivery.message_id,
            delivery.receipt_handle,
            delay,
        )
        self._metrics = _increment(self._metrics, "retries")
        logger.info(
            "worker retry scheduled",
            extra={
                "event": "worker.retry_scheduled",
                "message_id": delivery.message_id,
                "event_id": safe_event_id,
                "operation_id": delivery.operation_id,
                "attempt": delivery.receive_count,
                "classification": classification,
                "reason_code": reason_code,
                "delay_seconds": delay,
            },
        )
        return False

    async def run(self, stop_event: asyncio.Event) -> None:
        async def consume() -> None:
            while not stop_event.is_set():
                await self.process_once(long_poll=1.0)
                if self._queue.closed:
                    return

        tasks = [asyncio.create_task(consume()) for _ in range(self._concurrency)]
        stop_task = asyncio.create_task(stop_event.wait())
        await asyncio.wait([*tasks, stop_task], return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if not task.done():
                task.cancel()
        if not stop_task.done():
            stop_task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(stop_task, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                logger.error(
                    "worker consumer stopped unexpectedly",
                    extra={
                        "event": "worker.supervision_failure",
                        "error_type": type(result).__name__,
                    },
                )
                raise result


def _increment(metrics: WorkerMetrics, field: str) -> WorkerMetrics:
    values = {
        "inserted": metrics.inserted,
        "duplicates": metrics.duplicates,
        "conflicts": metrics.conflicts,
        "decode_failures": metrics.decode_failures,
        "processing_errors": metrics.processing_errors,
        "retries": metrics.retries,
        "dlq": metrics.dlq,
    }
    values[field] += 1
    return WorkerMetrics(**values)
