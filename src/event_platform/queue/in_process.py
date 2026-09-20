"""Bounded SQS-style in-process queue semantics."""

from __future__ import annotations

import asyncio
import heapq
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, cast
from uuid import uuid4

DLQClassification = Literal["transient", "permanent", "unknown"]
DLQReasonCode = Literal[
    "mongo_dependency",
    "invalid_envelope",
    "event_conflict",
    "unknown_failure",
    "max_receive_count",
]
_ALLOWED_CLASSIFICATIONS = frozenset({"transient", "permanent", "unknown"})
_ALLOWED_REASON_CODES = frozenset(
    {
        "mongo_dependency",
        "invalid_envelope",
        "event_conflict",
        "unknown_failure",
        "max_receive_count",
    }
)


class QueueClosed(RuntimeError):
    """The queue no longer accepts sends or receives."""


class QueueFull(TimeoutError):
    """Capacity was unavailable before the send deadline."""


class ReceiptHandleError(ValueError):
    """A receipt is stale, unknown, or belongs to another delivery."""


@dataclass(frozen=True, slots=True)
class Delivery:
    message_id: str
    body: Mapping[str, object]
    receipt_handle: str
    receive_count: int
    enqueued_at: float
    operation_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """A volatile DLQ copy with bounded safe disposition diagnostics."""

    delivery: Delivery
    classification: DLQClassification
    reason_code: DLQReasonCode
    attempts: int


@dataclass(frozen=True, slots=True)
class QueueStats:
    capacity: int
    depth: int
    visible: int
    in_flight: int
    dlq_depth: int
    oldest_age: float = 0.0


@dataclass(slots=True)
class _Message:
    message_id: str
    body: Mapping[str, object]
    enqueued_at: float
    visibility_deadline: float = 0.0
    receive_count: int = 0
    receipt_handle: str | None = None
    operation_id: str | None = None


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, tuple):
        return tuple(_freeze(child) for child in value)
    return value


class InProcessQueue:
    """Concurrency-safe bounded queue with visibility and receipt semantics."""

    def __init__(
        self,
        *,
        capacity: int,
        visibility_timeout: float = 30.0,
        send_timeout: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if visibility_timeout < 0 or send_timeout < 0:
            raise ValueError("timeouts must be non-negative")
        self._capacity = capacity
        self._visibility_timeout = visibility_timeout
        self._send_timeout = send_timeout
        self._clock = clock
        self._condition = asyncio.Condition()
        self._messages: dict[str, _Message] = {}
        self._ready: deque[_Message] = deque()
        self._expiry: list[tuple[float, int, str]] = []
        self._sequence = 0
        self._dlq: list[DeadLetter] = []
        self._accepting = True
        self._closed = False

    async def send(
        self,
        body: Mapping[str, object],
        *,
        message_id: str | None = None,
        operation_id: str | None = None,
    ) -> str:
        if message_id is not None and not _is_safe_identifier(message_id):
            raise ValueError("message_id must be 1-256 printable ASCII characters")
        if operation_id is not None and not _is_safe_identifier(operation_id):
            raise ValueError("operation_id must be 1-256 printable ASCII characters")
        deadline = self._clock() + self._send_timeout
        async with self._condition:
            while len(self._messages) >= self._capacity:
                self._ensure_open()
                if not self._accepting:
                    raise QueueClosed("queue is draining and no longer accepts sends")
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise QueueFull("queue capacity unavailable before send timeout")
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    raise QueueFull("queue capacity unavailable before send timeout") from None
            self._ensure_open()
            if not self._accepting:
                raise QueueClosed("queue is draining and no longer accepts sends")
            identifier = message_id or str(uuid4())
            message = _Message(
                identifier,
                cast(Mapping[str, object], _freeze(body)),
                self._clock(),
                operation_id=operation_id,
            )
            self._messages[identifier] = message
            self._ready.append(message)
            self._condition.notify_all()
            return identifier

    async def receive(self, *, long_poll: float = 0.0) -> Delivery:
        if long_poll < 0:
            raise ValueError("long_poll must be non-negative")
        deadline = self._clock() + long_poll
        async with self._condition:
            while True:
                self._ensure_open()
                now = self._clock()
                self._promote_expired(now)
                while self._ready:
                    message = self._ready.popleft()
                    if (
                        message.message_id not in self._messages
                        or message.visibility_deadline > now
                    ):
                        continue
                    message.receive_count += 1
                    message.receipt_handle = str(uuid4())
                    message.visibility_deadline = now + self._visibility_timeout
                    self._sequence += 1
                    heapq.heappush(
                        self._expiry,
                        (message.visibility_deadline, self._sequence, message.message_id),
                    )
                    return Delivery(
                        message.message_id,
                        message.body,
                        message.receipt_handle,
                        message.receive_count,
                        message.enqueued_at,
                        message.operation_id,
                    )
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError("long poll expired without a visible message")
                next_deadline = min(
                    (message.visibility_deadline for message in self._messages.values()),
                    default=deadline,
                )
                wait_for = min(remaining, max(0.0, next_deadline - now))
                await asyncio.wait_for(self._condition.wait(), timeout=wait_for or remaining)

    async def delete(self, message_id: str, receipt_handle: str) -> None:
        async with self._condition:
            message = self._current(message_id, receipt_handle)
            del self._messages[message.message_id]
            self._condition.notify_all()

    async def change_visibility(self, message_id: str, receipt_handle: str, timeout: float) -> None:
        if timeout < 0:
            raise ValueError("visibility timeout must be non-negative")
        async with self._condition:
            message = self._current(message_id, receipt_handle)
            message.visibility_deadline = self._clock() + timeout
            self._sequence += 1
            heapq.heappush(
                self._expiry, (message.visibility_deadline, self._sequence, message.message_id)
            )
            self._condition.notify_all()

    async def dead_letter(
        self,
        message_id: str,
        receipt_handle: str,
        *,
        classification: DLQClassification,
        reason_code: DLQReasonCode,
    ) -> None:
        """Move one current delivery to the volatile DLQ with safe diagnostics."""

        if classification not in _ALLOWED_CLASSIFICATIONS:
            raise ValueError("classification is not a supported safe value")
        if reason_code not in _ALLOWED_REASON_CODES:
            raise ValueError("reason_code is not a supported safe value")
        async with self._condition:
            message = self._current(message_id, receipt_handle)
            delivery = Delivery(
                message.message_id,
                message.body,
                message.receipt_handle or "",
                message.receive_count,
                message.enqueued_at,
                message.operation_id,
            )
            self._dlq.append(
                DeadLetter(delivery, classification, reason_code, message.receive_count)
            )
            del self._messages[message.message_id]
            self._condition.notify_all()

    async def redrive(self, *, max_receive_count: int) -> int:
        if max_receive_count < 1:
            raise ValueError("max_receive_count must be positive")
        async with self._condition:
            now = self._clock()
            moved = [
                message
                for message in self._messages.values()
                if message.receive_count >= max_receive_count and message.visibility_deadline <= now
            ]
            for message in moved:
                delivery = Delivery(
                    message.message_id,
                    message.body,
                    message.receipt_handle or "",
                    message.receive_count,
                    message.enqueued_at,
                    message.operation_id,
                )
                self._dlq.append(
                    DeadLetter(delivery, "unknown", "max_receive_count", message.receive_count)
                )
                del self._messages[message.message_id]
            self._condition.notify_all()
            return len(moved)

    async def stats(self) -> QueueStats:
        async with self._condition:
            now = self._clock()
            self._promote_expired(now)
            visible = sum(message.visibility_deadline <= now for message in self._messages.values())
            oldest_age = max(
                (max(0.0, now - message.enqueued_at) for message in self._messages.values()),
                default=0.0,
            )
            return QueueStats(
                self._capacity,
                len(self._messages),
                visible,
                len(self._messages) - visible,
                len(self._dlq),
                oldest_age,
            )

    async def dlq(self) -> tuple[Delivery, ...]:
        async with self._condition:
            return tuple(entry.delivery for entry in self._dlq)

    async def dlq_entries(self) -> tuple[DeadLetter, ...]:
        """Return DLQ entries including safe classification diagnostics."""

        async with self._condition:
            return tuple(self._dlq)

    @property
    def closed(self) -> bool:
        """Whether the queue has stopped accepting receives and sends."""

        return self._closed

    @property
    def visibility_timeout(self) -> float:
        """Configured delivery visibility interval for worker heartbeats."""

        return self._visibility_timeout

    @property
    def accepting(self) -> bool:
        """Whether new messages may be admitted."""

        return self._accepting and not self._closed

    @property
    def durable(self) -> bool:
        """The local adapter is intentionally volatile across process restarts."""

        return False

    def stop_accepting(self) -> None:
        """Stop new sends while allowing current deliveries to drain."""

        self._accepting = False
        try:
            asyncio.get_running_loop().create_task(self.wake())
        except RuntimeError:
            # A queue can be configured before an event loop exists. The
            # lifecycle supervisor awaits wake() when shutdown is requested.
            pass

    async def wake(self) -> None:
        """Wake timed waiters after an injected clock advances."""

        async with self._condition:
            self._condition.notify_all()

    async def close(self) -> None:
        async with self._condition:
            self._accepting = False
            self._closed = True
            self._condition.notify_all()

    def _ensure_open(self) -> None:
        if self._closed:
            raise QueueClosed("queue is closed")

    def _current(self, message_id: str, receipt_handle: str) -> _Message:
        message = self._messages.get(message_id)
        if message is not None and message.receipt_handle == receipt_handle:
            return message
        raise ReceiptHandleError("receipt handle is stale or unknown")

    def _promote_expired(self, now: float) -> None:
        while self._expiry and self._expiry[0][0] <= now:
            deadline, _, message_id = heapq.heappop(self._expiry)
            message = self._messages.get(message_id)
            if message is not None and message.visibility_deadline == deadline:
                self._ready.append(message)


def _is_safe_identifier(value: str) -> bool:
    return 0 < len(value) <= 256 and all(char.isascii() and char.isprintable() for char in value)
