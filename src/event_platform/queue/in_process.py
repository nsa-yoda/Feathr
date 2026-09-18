"""Bounded SQS-style in-process queue semantics."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import uuid4


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


@dataclass(frozen=True, slots=True)
class QueueStats:
    capacity: int
    depth: int
    visible: int
    in_flight: int
    dlq_depth: int


@dataclass(slots=True)
class _Message:
    message_id: str
    body: Mapping[str, object]
    enqueued_at: float
    visibility_deadline: float = 0.0
    receive_count: int = 0
    receipt_handle: str | None = None


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
        self._messages: list[_Message] = []
        self._dlq: list[Delivery] = []
        self._closed = False

    async def send(self, body: Mapping[str, object], *, message_id: str | None = None) -> str:
        deadline = self._clock() + self._send_timeout
        async with self._condition:
            while len(self._messages) >= self._capacity:
                self._ensure_open()
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise QueueFull("queue capacity unavailable before send timeout")
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                except TimeoutError:
                    raise QueueFull("queue capacity unavailable before send timeout") from None
            self._ensure_open()
            identifier = message_id or str(uuid4())
            self._messages.append(
                _Message(identifier, _freeze(body), self._clock())  # type: ignore[arg-type]
            )
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
                for message in self._messages:
                    if message.visibility_deadline <= now:
                        message.receive_count += 1
                        message.receipt_handle = str(uuid4())
                        message.visibility_deadline = now + self._visibility_timeout
                        return Delivery(
                            message.message_id,
                            message.body,
                            message.receipt_handle,
                            message.receive_count,
                            message.enqueued_at,
                        )
                remaining = deadline - now
                if remaining <= 0:
                    raise TimeoutError("long poll expired without a visible message")
                next_deadline = min(
                    (message.visibility_deadline for message in self._messages),
                    default=deadline,
                )
                wait_for = min(remaining, max(0.0, next_deadline - now))
                await asyncio.wait_for(self._condition.wait(), timeout=wait_for or remaining)

    async def delete(self, message_id: str, receipt_handle: str) -> None:
        async with self._condition:
            message = self._current(message_id, receipt_handle)
            self._messages.remove(message)
            self._condition.notify_all()

    async def change_visibility(self, message_id: str, receipt_handle: str, timeout: float) -> None:
        if timeout < 0:
            raise ValueError("visibility timeout must be non-negative")
        async with self._condition:
            message = self._current(message_id, receipt_handle)
            message.visibility_deadline = self._clock() + timeout
            self._condition.notify_all()

    async def redrive(self, *, max_receive_count: int) -> int:
        if max_receive_count < 1:
            raise ValueError("max_receive_count must be positive")
        async with self._condition:
            now = self._clock()
            moved = [
                message
                for message in self._messages
                if message.receive_count >= max_receive_count and message.visibility_deadline <= now
            ]
            for message in moved:
                self._messages.remove(message)
                self._dlq.append(
                    Delivery(
                        message.message_id,
                        message.body,
                        message.receipt_handle or "",
                        message.receive_count,
                        message.enqueued_at,
                    )
                )
            self._condition.notify_all()
            return len(moved)

    async def stats(self) -> QueueStats:
        async with self._condition:
            now = self._clock()
            visible = sum(message.visibility_deadline <= now for message in self._messages)
            return QueueStats(
                self._capacity,
                len(self._messages),
                visible,
                len(self._messages) - visible,
                len(self._dlq),
            )

    async def dlq(self) -> tuple[Delivery, ...]:
        async with self._condition:
            return tuple(self._dlq)

    async def wake(self) -> None:
        """Wake timed waiters after an injected clock advances."""

        async with self._condition:
            self._condition.notify_all()

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _ensure_open(self) -> None:
        if self._closed:
            raise QueueClosed("queue is closed")

    def _current(self, message_id: str, receipt_handle: str) -> _Message:
        for message in self._messages:
            if message.message_id == message_id and message.receipt_handle == receipt_handle:
                return message
        raise ReceiptHandleError("receipt handle is stale or unknown")
