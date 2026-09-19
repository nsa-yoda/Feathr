from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.projection import (
    ChangeStreamEvent,
    ProjectionError,
    RetryPolicy,
    SearchProjector,
)

pytestmark = pytest.mark.failure


def make_event() -> CanonicalEvent:
    source = EventInput.model_validate(
        {
            "event_type": "purchase",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "user-1",
            "source_url": "https://example.test/checkout",
            "metadata": {},
        }
    )
    return CanonicalEvent.from_input(
        source,
        event_id=UUID("00000000-0000-0000-0000-000000000002"),
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


class Checkpoint:
    def __init__(self) -> None:
        self.value = None

    async def load(self, projector: str) -> None:
        del projector
        return self.value

    async def save(self, checkpoint: object) -> None:
        self.value = checkpoint


class OutageWriter:
    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        del document_id, source, target_index
        raise ProjectionError("elasticsearch_unavailable", transient=True)


@pytest.mark.asyncio
async def test_elasticsearch_outage_retains_checkpoint_and_reports_retry_state() -> None:
    checkpoint = Checkpoint()
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=OutageWriter(),
    )
    await projector.start()
    with pytest.raises(ProjectionError):
        await projector.project_change(ChangeStreamEvent({"token": 1}, make_event()))
    assert checkpoint.value is None
    assert projector.status().state == "retrying"
    assert projector.status().failure_code == "elasticsearch_unavailable"


@pytest.mark.asyncio
async def test_checkpoint_and_change_stream_outages_are_bounded_and_visible() -> None:
    class DownCheckpoint:
        async def load(self, projector: str) -> None:
            del projector
            raise ProjectionError("checkpoint_unavailable", transient=True)

    projector = SearchProjector(
        projector="events-search", checkpoint=DownCheckpoint(), writer=OutageWriter()
    )
    status = await projector.start()
    assert status.state == "degraded"
    assert status.failure_code == "checkpoint_unavailable"

    class RecoveringCheckpoint:
        def __init__(self) -> None:
            self.attempts = 0

        async def load(self, projector: str):
            del projector
            self.attempts += 1
            if self.attempts == 1:
                raise ProjectionError("checkpoint_unavailable", transient=True)
            return None

        async def save(self, checkpoint: object) -> None:
            del checkpoint

    class EmptySource:
        def stream(self, *, resume_after: Mapping[str, object] | None = None):
            del resume_after

            async def items():
                if False:
                    yield ChangeStreamEvent({"token": 1}, make_event())

            return items()

    recovering_checkpoint = RecoveringCheckpoint()
    recovering = SearchProjector(
        projector="events-search",
        checkpoint=recovering_checkpoint,
        writer=OutageWriter(),
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2),
        sleep=lambda _delay: _instant_sleep(),
    )
    assert (await recovering.run_source(EmptySource())).state == "running"
    assert recovering_checkpoint.attempts == 2

    class FlakySource:
        def __init__(self) -> None:
            self.attempts = 0

        def stream(self, *, resume_after: Mapping[str, object] | None = None):
            del resume_after
            self.attempts += 1

            async def items():
                if self.attempts == 1:
                    raise ProjectionError("dependency_unavailable", transient=True)
                yield ChangeStreamEvent({"token": self.attempts}, make_event())

            return items()

    class WorkingWriter:
        async def write(
            self,
            document_id: str,
            source: Mapping[str, object],
            *,
            target_index: str | None = None,
        ) -> None:
            del document_id, source, target_index

    class Checkpoint:
        def __init__(self) -> None:
            self.value = None

        async def load(self, projector: str):
            del projector
            return self.value

        async def save(self, checkpoint: object) -> None:
            self.value = checkpoint

    checkpoint = Checkpoint()
    source = FlakySource()
    recovering = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=WorkingWriter(),
        retry_policy=RetryPolicy(initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2),
        sleep=lambda _delay: _instant_sleep(),
    )
    status = await recovering.run_source(source)
    assert status.state == "running"
    assert source.attempts == 2
    assert checkpoint.value is not None


async def _instant_sleep() -> None:
    return None
