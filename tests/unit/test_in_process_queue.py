"""Deterministic SQS-style queue semantics."""

from __future__ import annotations

import asyncio

import pytest

from event_platform.queue import (
    InProcessQueue,
    QueueClosed,
    QueueFull,
    ReceiptHandleError,
)

pytestmark = pytest.mark.unit


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.mark.asyncio
async def test_send_receive_delete_and_immutable_body() -> None:
    queue = InProcessQueue(capacity=2)
    message_id = await queue.send({"event": "pageview", "tags": ["new"]})
    delivery = await queue.receive()

    assert delivery.message_id == message_id
    assert delivery.receive_count == 1
    with pytest.raises(TypeError):
        delivery.body["event"] = "changed"  # type: ignore[index]
    await queue.delete(delivery.message_id, delivery.receipt_handle)
    assert (await queue.stats()).depth == 0


@pytest.mark.asyncio
async def test_stale_receipts_and_visibility_expiry_redeliver() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=10, clock=clock)
    message_id = await queue.send({"value": 1})
    first = await queue.receive()
    with pytest.raises(TimeoutError):
        await queue.receive(long_poll=0)

    clock.advance(10)
    second_task = asyncio.create_task(queue.receive())
    await queue.wake()
    second = await second_task
    assert second.message_id == message_id
    assert second.receive_count == 2
    assert second.receipt_handle != first.receipt_handle
    with pytest.raises(ReceiptHandleError):
        await queue.delete(message_id, first.receipt_handle)
    await queue.delete(message_id, second.receipt_handle)


@pytest.mark.asyncio
async def test_long_poll_wakes_on_send_and_capacity_timeout_is_bounded() -> None:
    queue = InProcessQueue(capacity=1, send_timeout=0.01)
    waiter = asyncio.create_task(queue.receive(long_poll=1))
    await asyncio.sleep(0)
    await queue.send({"ready": True})
    assert (await waiter).body["ready"] is True

    full = InProcessQueue(capacity=1, send_timeout=0.01)
    await full.send({"occupied": True})
    with pytest.raises(QueueFull):
        await full.send({"blocked": True})


@pytest.mark.asyncio
async def test_concurrent_consumers_get_distinct_messages() -> None:
    queue = InProcessQueue(capacity=3)
    for value in range(3):
        await queue.send({"value": value})
    deliveries = await asyncio.gather(*(queue.receive() for _ in range(3)))
    assert len({delivery.message_id for delivery in deliveries}) == 3
    assert (await queue.stats()).in_flight == 3


@pytest.mark.asyncio
async def test_close_wakes_waiters_and_allows_inflight_delete() -> None:
    queue = InProcessQueue(capacity=1)
    await queue.send({"value": 1})
    delivery = await queue.receive()
    waiter = asyncio.create_task(queue.receive(long_poll=10))
    await asyncio.sleep(0)
    await queue.close()
    with pytest.raises(QueueClosed):
        await waiter
    await queue.delete(delivery.message_id, delivery.receipt_handle)
    with pytest.raises(QueueClosed):
        await queue.send({"after": "close"})


@pytest.mark.asyncio
async def test_redrive_moves_expired_repeated_delivery_to_dlq() -> None:
    clock = ManualClock()
    queue = InProcessQueue(capacity=1, visibility_timeout=1, clock=clock)
    await queue.send({"value": "dead"})
    first = await queue.receive()
    clock.advance(1)
    second = await queue.receive()
    assert second.receive_count == 2
    clock.advance(1)
    assert await queue.redrive(max_receive_count=2) == 1
    assert (await queue.stats()).dlq_depth == 1
    assert (await queue.dlq())[0].message_id == first.message_id
