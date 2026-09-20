"""Checkpointed, replay-safe Mongo-to-Elasticsearch projection."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from event_platform.domain.events import CanonicalEvent
from event_platform.observability.metrics import MetricsRegistry
from event_platform.search.mapping import project_search_document

logger = logging.getLogger("event_platform.search_projection")

ProjectionState = Literal[
    "starting",
    "running",
    "retrying",
    "degraded",
    "reconciliation_required",
    "stopped",
]
SAFE_FAILURE_CODES = frozenset(
    {
        "resume_history_invalid",
        "change_malformed",
        "elasticsearch_unavailable",
        "elasticsearch_rejected",
        "checkpoint_unavailable",
        "checkpoint_invalid",
        "dependency_unavailable",
        "retry_exhausted",
        "projector_stopped",
        "projection_owner_lost",
    }
)


class ProjectionError(RuntimeError):
    """Safe projector failure with an allowlisted operation code."""

    def __init__(self, code: str, *, transient: bool = False) -> None:
        if code not in SAFE_FAILURE_CODES:
            raise ValueError("unsupported projection failure code")
        super().__init__(code)
        self.code = code
        self.transient = transient


class InvalidResumeHistory(ProjectionError):
    def __init__(self) -> None:
        super().__init__("resume_history_invalid")


class MalformedChange(ProjectionError):
    def __init__(self) -> None:
        super().__init__("change_malformed")


@dataclass(frozen=True, slots=True)
class ProjectionCheckpoint:
    projector: str
    resume_token: Mapping[str, object]
    state: ProjectionState = "running"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_projected_event_at: datetime | None = None
    failure_code: str | None = None
    owner: str = "events-search"
    generation: int = 0
    source_position: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectionStatus:
    state: ProjectionState
    checkpoint_present: bool
    last_success_at: datetime | None
    last_projected_event_at: datetime | None
    lag_seconds: float | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class ChangeStreamEvent:
    resume_token: Mapping[str, object]
    event: CanonicalEvent
    source_position: str | None = None


class CheckpointPort(Protocol):
    async def load(self, projector: str) -> ProjectionCheckpoint | None: ...

    async def save(self, checkpoint: ProjectionCheckpoint) -> None: ...


class ProjectionWriter(Protocol):
    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None: ...

    async def bulk_write(
        self,
        documents: Sequence[tuple[str, Mapping[str, object]]],
        *,
        target_index: str | None = None,
    ) -> None: ...


class ChangeStreamPort(Protocol):
    def stream(
        self, *, resume_after: Mapping[str, object] | None = None
    ) -> AsyncIterator[ChangeStreamEvent]: ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    initial_delay: float = 0.25
    multiplier: float = 2.0
    max_delay: float = 30.0
    jitter_ratio: float = 0.2
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if self.initial_delay < 0 or self.multiplier < 1 or self.max_delay < 0:
            raise ValueError("retry policy bounds are invalid")
        if not 0 <= self.jitter_ratio <= 1 or self.max_attempts < 1:
            raise ValueError("retry policy bounds are invalid")

    def delay(self, attempt: int, *, jitter: Callable[[], float] = random.random) -> float:
        if attempt < 1:
            raise ValueError("retry attempt must be positive")
        base = min(self.max_delay, self.initial_delay * self.multiplier ** (attempt - 1))
        return min(self.max_delay, base * (1 + self.jitter_ratio * jitter()))


def project_event(event: CanonicalEvent) -> dict[str, object]:
    """Create a deterministic, JSON-safe source from canonical event fields."""

    source = project_search_document(event)
    source["timestamp"] = event.timestamp.astimezone(UTC).isoformat()
    source["ingested_at"] = event.ingested_at.astimezone(UTC).isoformat()
    source["metadata"] = _copy_json(source["metadata"])
    return source


def _copy_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _copy_json(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_copy_json(child) for child in value]
    return value


class SearchProjector:
    """Coordinate ordered projection, checkpointing, status, retry, and shutdown."""

    def __init__(
        self,
        *,
        projector: str,
        checkpoint: CheckpointPort,
        writer: ProjectionWriter,
        owner: str = "events-search",
        generation: int = 0,
        target_index: str | None = None,
        retry_policy: RetryPolicy | None = None,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not projector or len(projector) > 64:
            raise ValueError("projector name is invalid")
        if not owner or len(owner) > 128 or generation < 0:
            raise ValueError("projection ownership is invalid")
        self.projector = projector
        self._owner = owner
        self._generation = generation
        self._checkpoint = checkpoint
        self._writer = writer
        self._target_index = target_index
        self._retry_policy = retry_policy or RetryPolicy()
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._metrics = metrics
        self._stop_requested = False
        self._current: ProjectionCheckpoint | None = None
        self._status = ProjectionStatus("starting", False, None, None, None, None)

    async def start(self) -> ProjectionStatus:
        try:
            loaded = await self._checkpoint.load(self.projector)
        except ProjectionError as error:
            if error.code == "checkpoint_invalid":
                return self.mark_reconciliation_required()
            self._status = ProjectionStatus(
                "degraded",
                self._current is not None,
                self._status.last_success_at,
                self._status.last_projected_event_at,
                self._status.lag_seconds,
                error.code,
            )
            self._emit("projector.failure", state="degraded", failure_code=error.code)
            return self._status
        self._current = loaded
        if self._stop_requested:
            self._status = ProjectionStatus(
                "stopped",
                self._current is not None,
                self._status.last_success_at,
                self._status.last_projected_event_at,
                self._status.lag_seconds,
                self._status.failure_code,
            )
            return self._status
        if self._current is None:
            self._status = ProjectionStatus("running", False, None, None, None, None)
        else:
            self._status = self._status_from_checkpoint(self._current)
        self._emit("projector.start", state=self._status.state)
        return self._status

    async def set_target_index(self, target_index: str | None) -> None:
        """Atomically change the optional rebuild target used by subsequent writes."""

        if target_index is not None and (not target_index or len(target_index) > 255):
            raise ValueError("projection target index is invalid")
        self._target_index = target_index

    def set_ownership(self, *, owner: str, generation: int) -> None:
        """Set the lease owner before consuming the source stream."""

        if self._current is not None or self._status.state not in {"starting", "stopped"}:
            raise RuntimeError("projection ownership can only change before start")
        if not owner or len(owner) > 128 or generation < 1:
            raise ValueError("projection ownership is invalid")
        self._owner = owner
        self._generation = generation

    async def project_change(self, change: ChangeStreamEvent) -> ProjectionStatus:
        if self._stop_requested:
            raise ProjectionError("projector_stopped")
        if not change.resume_token:
            raise MalformedChange()
        source = project_event(change.event)
        try:
            await self._writer.write(
                str(change.event.event_id), source, target_index=self._target_index
            )
            checkpoint = ProjectionCheckpoint(
                projector=self.projector,
                resume_token=dict(change.resume_token),
                state="running",
                updated_at=self._now(),
                last_projected_event_at=change.event.timestamp,
                owner=self._owner,
                generation=self._generation,
                source_position=change.source_position
                or (self._current.source_position if self._current else None),
            )
            await self._checkpoint.save(checkpoint)
        except ProjectionError as error:
            self._status = ProjectionStatus(
                "retrying" if error.transient else "degraded",
                self._current is not None,
                self._status.last_success_at,
                self._status.last_projected_event_at,
                self._status.lag_seconds,
                error.code,
            )
            self._emit("projector.failure", state=self._status.state, failure_code=error.code)
            raise
        self._current = checkpoint
        self._status = self._status_from_checkpoint(checkpoint)
        self._emit("projector.success", state="running")
        return self._status

    async def project_batch(self, changes: Sequence[ChangeStreamEvent]) -> ProjectionStatus:
        """Project a bounded batch without creating one task per change."""

        if len(changes) > 1_000:
            raise ValueError("projection batch is too large")
        bulk_write = getattr(self._writer, "bulk_write", None)
        if len(changes) > 1 and callable(bulk_write):
            documents = [
                (str(change.event.event_id), project_event(change.event)) for change in changes
            ]
            await bulk_write(documents, target_index=self._target_index)
            for change in changes:
                checkpoint = ProjectionCheckpoint(
                    projector=self.projector,
                    resume_token=dict(change.resume_token),
                    state="running",
                    updated_at=self._now(),
                    last_projected_event_at=change.event.timestamp,
                    owner=self._owner,
                    generation=self._generation,
                    source_position=change.source_position
                    or (self._current.source_position if self._current else None),
                )
                await self._checkpoint.save(checkpoint)
                self._current = checkpoint
                self._status = self._status_from_checkpoint(checkpoint)
            self._emit("projector.bulk_success", state="running", batch_size=len(changes))
            return self._status
        for change in changes:
            await self.project_change(change)
        return self._status

    async def run(self, stream: AsyncIterator[ChangeStreamEvent]) -> ProjectionStatus:
        """Consume a stream until shutdown, terminal failure, or cancellation."""

        await self.start()
        if self._status.state != "running":
            return self._status
        return await self._consume(stream)

    async def _consume(self, stream: AsyncIterator[ChangeStreamEvent]) -> ProjectionStatus:
        if self._status.state == "reconciliation_required":
            return self._status
        pending_next: asyncio.Task[ChangeStreamEvent] | None = None
        try:
            iterator = stream.__aiter__()
            exhausted = False

            async def next_change() -> ChangeStreamEvent:
                return await iterator.__anext__()

            while not exhausted and not self._stop_requested:
                try:
                    if pending_next is None:
                        pending_next = asyncio.create_task(next_change())
                    first = await pending_next
                    pending_next = None
                except StopAsyncIteration:
                    break
                changes = [first]
                source_error: ProjectionError | None = None
                bulk_enabled = callable(getattr(self._writer, "bulk_write", None))
                while bulk_enabled and len(changes) < 100:
                    try:
                        if pending_next is None:
                            pending_next = asyncio.create_task(next_change())
                        changes.append(
                            await asyncio.wait_for(asyncio.shield(pending_next), timeout=0.005)
                        )
                        pending_next = None
                    except TimeoutError:
                        break
                    except StopAsyncIteration:
                        pending_next = None
                        exhausted = True
                        break
                    except ProjectionError as error:
                        pending_next = None
                        source_error = error
                        break
                if self._stop_requested:
                    break
                try:
                    await self.project_batch(changes)
                except ProjectionError as error:
                    for change in changes:
                        try:
                            await self._project_with_retry(change, error)
                        except ProjectionError as terminal:
                            self._status = ProjectionStatus(
                                "degraded",
                                self._status.checkpoint_present,
                                self._status.last_success_at,
                                self._status.last_projected_event_at,
                                self._status.lag_seconds,
                                terminal.code,
                            )
                            exhausted = True
                            break
                if source_error is not None:
                    raise source_error
        except InvalidResumeHistory:
            return self.mark_reconciliation_required()
        except ProjectionError as error:
            self._status = ProjectionStatus(
                "degraded",
                self._status.checkpoint_present,
                self._status.last_success_at,
                self._status.last_projected_event_at,
                self._status.lag_seconds,
                error.code,
            )
            self._emit("projector.failure", state="degraded", failure_code=error.code)
        finally:
            # A shielded look-ahead must not outlive the projector during
            # shutdown; otherwise a Mongo change stream can keep the task
            # tree alive past the lifecycle grace period.
            if pending_next is not None and not pending_next.done():
                pending_next.cancel()
            # PyMongo may not observe cancellation until its socket timeout.
            # Do not make application shutdown wait on that I/O task; consume
            # its eventual result when it does finish to avoid warnings.
            if pending_next is not None and pending_next.done():
                try:
                    pending_next.exception()
                except asyncio.CancelledError:
                    pass
        return self._status

    async def _project_with_retry(
        self, change: ChangeStreamEvent, initial_error: ProjectionError
    ) -> ProjectionStatus:
        if not initial_error.transient:
            raise initial_error
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                return await self.retry_change(change, attempt)
            except ProjectionError as retry_error:
                if not retry_error.transient:
                    break
        raise ProjectionError("retry_exhausted")

    async def run_source(self, source: ChangeStreamPort) -> ProjectionStatus:
        """Resume from the stored token and consume a source's insert stream."""

        for attempt in range(1, self._retry_policy.max_attempts + 1):
            if self._stop_requested:
                return self._status
            status = await self.start()
            if status.state == "reconciliation_required":
                return status
            if status.state != "running":
                if status.failure_code != "checkpoint_unavailable":
                    return status
                if attempt == self._retry_policy.max_attempts:
                    self._status = ProjectionStatus(
                        "degraded",
                        self._current is not None,
                        self._status.last_success_at,
                        self._status.last_projected_event_at,
                        self._status.lag_seconds,
                        "retry_exhausted",
                    )
                    return self._status
                await self._schedule_retry(attempt)
                continue
            if self._stop_requested:
                return self._status
            resume_after = self._current.resume_token if self._current else None
            status = await self._consume(source.stream(resume_after=resume_after))
            if status.failure_code != "dependency_unavailable":
                return status
            if attempt == self._retry_policy.max_attempts:
                self._status = ProjectionStatus(
                    "degraded",
                    self._status.checkpoint_present,
                    self._status.last_success_at,
                    self._status.last_projected_event_at,
                    self._status.lag_seconds,
                    "retry_exhausted",
                )
                return self._status
            await self._schedule_retry(attempt)
        return self._status

    async def _schedule_retry(self, attempt: int) -> None:
        delay = self._retry_policy.delay(attempt)
        self._status = ProjectionStatus(
            "retrying",
            self._status.checkpoint_present,
            self._status.last_success_at,
            self._status.last_projected_event_at,
            self._status.lag_seconds,
            "dependency_unavailable",
        )
        self._emit("projector.retry_scheduled", attempt=attempt)
        await self._sleep(delay)

    async def retry_change(self, change: ChangeStreamEvent, attempt: int) -> ProjectionStatus:
        if attempt > self._retry_policy.max_attempts:
            raise ProjectionError("retry_exhausted")
        delay = self._retry_policy.delay(attempt)
        self._status = ProjectionStatus(
            "retrying",
            self._current is not None,
            self._status.last_success_at,
            self._status.last_projected_event_at,
            self._status.lag_seconds,
            "dependency_unavailable",
        )
        self._emit("projector.retry_scheduled", attempt=attempt)
        await self._sleep(delay)
        return await self.project_change(change)

    def mark_reconciliation_required(self) -> ProjectionStatus:
        self._status = ProjectionStatus(
            "reconciliation_required",
            self._current is not None,
            self._status.last_success_at,
            self._status.last_projected_event_at,
            self._status.lag_seconds,
            "resume_history_invalid",
        )
        self._emit("projector.reconciliation_required", state=self._status.state)
        return self._status

    def stop(self) -> ProjectionStatus:
        self._stop_requested = True
        self._status = ProjectionStatus(
            "stopped",
            self._status.checkpoint_present,
            self._status.last_success_at,
            self._status.last_projected_event_at,
            self._status.lag_seconds,
            self._status.failure_code,
        )
        self._emit("projector.shutdown", state="stopped")
        return self._status

    def status(self) -> ProjectionStatus:
        self._record_lag()
        return self._status

    def source_position(self) -> str | None:
        """Return the latest canonical Mongo position acknowledged by this projector."""

        return self._current.source_position if self._current is not None else None

    def checkpoint_marker(self) -> str | None:
        """Return the durable source position used for rebuild convergence evidence."""

        return self.source_position()

    def _status_from_checkpoint(self, checkpoint: ProjectionCheckpoint) -> ProjectionStatus:
        now = self._now()
        last_event = checkpoint.last_projected_event_at
        lag = max(0.0, (now - last_event).total_seconds()) if last_event else None
        status = ProjectionStatus(
            checkpoint.state,
            True,
            checkpoint.updated_at,
            last_event,
            lag,
            checkpoint.failure_code,
        )
        self._record_lag(status)
        return status

    def _record_lag(self, status: ProjectionStatus | None = None) -> None:
        if self._metrics is not None:
            current = status or self._status
            self._metrics.set_gauge(
                "event_platform_projection_lag_seconds",
                current.lag_seconds or 0.0,
                {"component": "search_projector"},
            )

    def _emit(self, event: str, **fields: object) -> None:
        logger.info(event, extra={"event": event, "projector": self.projector, **fields})
