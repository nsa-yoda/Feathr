"""Deterministic lifecycle supervision and bounded drain coverage."""

import asyncio

import pytest

from event_platform.core.lifecycle import LifecycleSupervisor, TaskPolicy
from event_platform.queue import InProcessQueue, QueueClosed

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_shutdown_stops_admission_before_draining_and_closes_in_order() -> None:
    queue = InProcessQueue(capacity=4)
    await queue.send({"event": "queued"})
    order: list[str] = []

    async def close(name: str) -> None:
        order.append(name)

    supervisor = LifecycleSupervisor(
        queue,
        grace_period=0.05,
        resources=[
            ("queue", queue.close),
            ("redis", lambda: close("redis")),
            ("mongo", lambda: close("mongo")),
        ],
    )

    async def worker(stop_event: asyncio.Event) -> None:
        await stop_event.wait()

    await supervisor.start({"persistence_worker": worker})
    await supervisor.request_shutdown()
    with pytest.raises(QueueClosed):
        await queue.send({"event": "rejected"})
    snapshot = await supervisor.shutdown()

    assert snapshot.state == "stopped"
    assert snapshot.queue_depth == 1
    assert queue.closed
    assert order == ["redis", "mongo"]


@pytest.mark.asyncio
async def test_unexpected_task_exit_marks_lifecycle_failed() -> None:
    queue = InProcessQueue(capacity=2)
    supervisor = LifecycleSupervisor(queue, grace_period=0.05)

    async def broken(_: asyncio.Event) -> None:
        return

    await supervisor.start({"persistence_worker": broken})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert supervisor.state == "failed"
    assert supervisor.failure_type == "RuntimeError"
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_slow_task_after_grace_period() -> None:
    queue = InProcessQueue(capacity=2)
    supervisor = LifecycleSupervisor(queue, grace_period=0.001)
    cancelled = asyncio.Event()

    async def slow(stop_event: asyncio.Event) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    await supervisor.start({"search_projector": slow})
    snapshot = await supervisor.shutdown()

    assert cancelled.is_set()
    assert snapshot.state == "stopped"


@pytest.mark.asyncio
async def test_resource_close_failure_marks_lifecycle_failed_but_continues() -> None:
    queue = InProcessQueue(capacity=2)
    closed: list[str] = []

    async def broken_close() -> None:
        closed.append("redis")
        raise OSError("close failed")

    async def final_close() -> None:
        closed.append("mongo")

    supervisor = LifecycleSupervisor(
        queue,
        resources=[("queue", queue.close), ("redis", broken_close), ("mongo", final_close)],
    )
    await supervisor.start()
    snapshot = await supervisor.shutdown()

    assert closed == ["redis", "mongo"]
    assert snapshot.state == "failed"
    assert snapshot.failure_type == "ResourceCloseError"


@pytest.mark.asyncio
async def test_unexpected_task_cancellation_marks_lifecycle_failed() -> None:
    queue = InProcessQueue(capacity=2)
    supervisor = LifecycleSupervisor(queue)

    async def worker(_: asyncio.Event) -> None:
        await asyncio.sleep(60)

    await supervisor.start({"worker": worker})
    await asyncio.sleep(0)
    supervisor._tasks["worker"].cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert supervisor.state == "failed"
    assert supervisor.failure_type == "RuntimeError"
    assert not queue.accepting
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_start_validates_all_task_names_before_creating_tasks() -> None:
    queue = InProcessQueue(capacity=2)
    supervisor = LifecycleSupervisor(queue)

    async def worker(_: asyncio.Event) -> None:
        await asyncio.sleep(60)

    with pytest.raises(ValueError, match="task name"):
        await supervisor.start({"worker": worker, "": worker})

    assert supervisor.state == "starting"
    assert not supervisor._tasks


@pytest.mark.asyncio
async def test_concurrent_shutdown_closes_resources_once() -> None:
    queue = InProcessQueue(capacity=2)
    close_count = 0

    async def close() -> None:
        nonlocal close_count
        close_count += 1

    supervisor = LifecycleSupervisor(queue, resources=[("resource", close)])
    await supervisor.start()
    await asyncio.gather(supervisor.shutdown(), supervisor.shutdown())

    assert close_count == 1


@pytest.mark.asyncio
async def test_stop_accepting_wakes_a_sender_waiting_on_full_queue() -> None:
    queue = InProcessQueue(capacity=1, send_timeout=10.0)
    await queue.send({"event": "full"})
    blocked = asyncio.create_task(queue.send({"event": "blocked"}))
    await asyncio.sleep(0)

    queue.stop_accepting()

    with pytest.raises(QueueClosed):
        await asyncio.wait_for(blocked, timeout=0.2)


@pytest.mark.asyncio
async def test_shutdown_does_not_close_resources_used_by_cancellation_resistant_task() -> None:
    queue = InProcessQueue(capacity=2)
    closed = False
    release = asyncio.Event()

    async def close() -> None:
        nonlocal closed
        closed = True

    async def resistant(_: asyncio.Event) -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                continue

    supervisor = LifecycleSupervisor(queue, grace_period=0.001, resources=[("mongo", close)])
    await supervisor.start({"persistence_worker": resistant})
    snapshot = await supervisor.shutdown()

    assert snapshot.state == "failed"
    assert not closed
    release.set()
    supervisor._tasks["persistence_worker"].cancel()
    await asyncio.gather(supervisor._tasks["persistence_worker"], return_exceptions=True)


def test_snapshot_rejects_invalid_invariants() -> None:
    from event_platform.core.lifecycle import LifecycleSnapshot

    with pytest.raises(ValueError, match="queue_depth"):
        LifecycleSnapshot("running", True, (), -1)
    with pytest.raises(ValueError, match="stopped"):
        LifecycleSnapshot("stopped", True, (), 0)


def test_task_policy_is_bounded_and_explicit() -> None:
    assert TaskPolicy("degradable", restart_limit=2, restart_backoff=1).criticality == "degradable"
    with pytest.raises(ValueError):
        TaskPolicy(restart_limit=11)
