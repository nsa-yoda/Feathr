"""Failure behavior for lifecycle supervision and resource cleanup."""

import asyncio

import pytest

from event_platform.core.lifecycle import LifecycleSupervisor
from event_platform.queue import InProcessQueue

pytestmark = pytest.mark.failure


@pytest.mark.asyncio
async def test_supervision_failure_is_safe_and_does_not_skip_resource_cleanup(caplog) -> None:
    queue = InProcessQueue(capacity=2)
    closed: list[str] = []

    async def broken(_: asyncio.Event) -> None:
        raise ConnectionError("secret endpoint must not be logged")

    async def failing_close() -> None:
        closed.append("redis")
        raise OSError("secret close detail")

    async def successful_close() -> None:
        closed.append("mongo")

    supervisor = LifecycleSupervisor(
        queue,
        grace_period=0.05,
        resources=[("queue", queue.close), ("redis", failing_close), ("mongo", successful_close)],
    )
    await supervisor.start({"persistence_worker": broken})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    snapshot = await supervisor.shutdown()

    assert snapshot.state == "failed"
    assert snapshot.failure_type == "ConnectionError"
    assert closed == ["redis", "mongo"]
    assert "secret endpoint" not in caplog.text
    assert "secret close detail" not in caplog.text
