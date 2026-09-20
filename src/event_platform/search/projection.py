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
        try:
            async for change in stream:
                if self._stop_requested:
                    break
                try:
                    await self.project_change(change)
                except ProjectionError as error:
                    if not error.transient:
                        self._status = ProjectionStatus(
                            "degraded",
                            self._status.checkpoint_present,
                            self._status.last_success_at,
                            self._status.last_projected_event_at,
                            self._status.lag_seconds,
                            error.code,
                        )
                        break
                    recovered = False
                    for attempt in range(1, self._retry_policy.max_attempts + 1):
                        try:
                            await self.retry_change(change, attempt)
                        except ProjectionError as retry_error:
                            if not retry_error.transient:
                                break
                        else:
                            recovered = True
                            break
                    if not recovered:
                        self._status = ProjectionStatus(
                            "degraded",
                            self._status.checkpoint_present,
                            self._status.last_success_at,
                            self._status.last_projected_event_at,
                            self._status.lag_seconds,
                            "retry_exhausted",
                        )
                        break
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
        return self._status

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
        return self._status

    def _status_from_checkpoint(self, checkpoint: ProjectionCheckpoint) -> ProjectionStatus:
        now = self._now()
        last_event = checkpoint.last_projected_event_at
        lag = max(0.0, (now - last_event).total_seconds()) if last_event else None
        return ProjectionStatus(
            checkpoint.state,
            True,
            checkpoint.updated_at,
            last_event,
            lag,
            checkpoint.failure_code,
        )

    def _emit(self, event: str, **fields: object) -> None:
        logger.info(event, extra={"event": event, "projector": self.projector, **fields})
