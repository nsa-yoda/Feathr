from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from event_platform.storage.idempotency import InMemoryIdempotencyRegistry

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_registry_reserves_replays_and_conflicts_without_raw_key_output() -> None:
    registry = InMemoryIdempotencyRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    event_id = UUID(int=1)
    first = await registry.reserve(
        scope="tenant-a",
        key="secret-key",
        operation="events.create",
        fingerprint="a" * 64,
        event_id=event_id,
        now=now,
        replay_window=timedelta(hours=1),
    )
    assert first.outcome == "new"
    assert (
        await registry.reserve(
            scope="tenant-a",
            key="secret-key",
            operation="events.create",
            fingerprint="a" * 64,
            event_id=UUID(int=2),
            now=now,
            replay_window=timedelta(hours=1),
        )
    ).outcome == "in_flight"
    await registry.complete(
        scope="tenant-a", key="secret-key", operation="events.create", event_id=event_id
    )
    replay = await registry.reserve(
        scope="tenant-a",
        key="secret-key",
        operation="events.create",
        fingerprint="a" * 64,
        event_id=UUID(int=3),
        now=now,
        replay_window=timedelta(hours=1),
    )
    assert replay.outcome == "replay"
    assert replay.event_id == event_id
    conflict = await registry.reserve(
        scope="tenant-a",
        key="secret-key",
        operation="events.create",
        fingerprint="b" * 64,
        event_id=UUID(int=4),
        now=now,
        replay_window=timedelta(hours=1),
    )
    assert conflict.outcome == "conflict"


@pytest.mark.asyncio
async def test_registry_release_is_owner_fenced_and_allows_retry_after_queue_failure() -> None:
    registry = InMemoryIdempotencyRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = await registry.reserve(
        scope="tenant-a",
        key="queue-failure",
        operation="events.create",
        fingerprint="a" * 64,
        event_id=UUID(int=1),
        now=now,
        replay_window=timedelta(hours=1),
    )
    await registry.release(
        scope="tenant-a",
        key="queue-failure",
        operation="events.create",
        event_id=UUID(int=1),
        reservation_token="wrong-owner",
    )
    assert (
        await registry.reserve(
            scope="tenant-a",
            key="queue-failure",
            operation="events.create",
            fingerprint="a" * 64,
            event_id=UUID(int=2),
            now=now,
            replay_window=timedelta(hours=1),
        )
    ).outcome == "in_flight"
    await registry.release(
        scope="tenant-a",
        key="queue-failure",
        operation="events.create",
        event_id=UUID(int=1),
        reservation_token=first.reservation_token,
    )
    retry = await registry.reserve(
        scope="tenant-a",
        key="queue-failure",
        operation="events.create",
        fingerprint="a" * 64,
        event_id=UUID(int=2),
        now=now,
        replay_window=timedelta(hours=1),
    )
    assert retry.outcome == "new"
