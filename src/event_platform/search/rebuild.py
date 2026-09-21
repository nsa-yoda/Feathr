"""Durable, verified Elasticsearch generation rebuild orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo import AsyncMongoClient

from event_platform.core.logging import configure_logging
from event_platform.core.settings import SettingsStartupError, load_settings
from event_platform.domain.events import CanonicalEvent
from event_platform.search.mapping import (
    INDEX_MAPPING,
    SEARCH_ALIAS,
    index_name,
    project_search_document,
)

logger = logging.getLogger("event_platform.search_rebuild")

SAFE_REBUILD_ERROR_CODES = frozenset(
    {
        "alias_swap_failed",
        "bulk_document_invalid",
        "bulk_failed",
        "bulk_rejected",
        "bulk_retry_exhausted",
        "bulk_unavailable",
        "count_failed",
        "count_invalid",
        "elasticsearch_unavailable",
        "index_cleanup_failed",
        "index_create_failed",
        "rebuild_lease_lost",
        "rebuild_lease_unavailable",
        "rebuild_unexpected_failure",
        "rebuild_verification_failed",
        "source_boundary_failed",
        "projection_convergence_timeout",
        "rebuild_state_persist_failed",
    }
)


class RebuildPhase(StrEnum):
    ACQUIRING = "acquiring"
    INDEX_CREATING = "index_creating"
    BULK_INDEXING = "bulk_indexing"
    RECONCILING = "reconciling"
    VERIFYING = "verifying"
    SWAPPING = "swapping"
    COMPLETED = "completed"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class RebuildError(RuntimeError):
    """Safe rebuild failure with a bounded category."""

    def __init__(self, code: str, *, transient: bool = False) -> None:
        safe_code = code if code in SAFE_REBUILD_ERROR_CODES else "rebuild_unexpected_failure"
        super().__init__(safe_code)
        self.code = safe_code
        self.transient = transient


class RebuildFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=64)
    count: int = Field(default=1, ge=1, le=1_000_000)


class RebuildRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rebuild_id: UUID
    phase: RebuildPhase
    started_at: datetime
    completed_at: datetime | None = None
    source_collection: str = Field(min_length=1, max_length=128)
    old_index: str | None = Field(default=None, max_length=255)
    target_index: str = Field(min_length=1, max_length=255)
    scanned_count: int = Field(default=0, ge=0)
    indexed_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    failures: tuple[RebuildFailure, ...] = Field(default_factory=tuple, max_length=32)
    owner: str = Field(min_length=1, max_length=128)
    lease_expires_at: datetime
    rollback_until: datetime | None = None
    backfill_upper_bound: str | None = Field(default=None, max_length=256)
    change_stream_position: str | None = Field(default=None, max_length=64)
    projector_change_stream_position: str | None = Field(default=None, max_length=64)
    fencing_token: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def migrate_boundary_names(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "backfill_upper_bound" not in data and "source_high_water" in data:
            data["backfill_upper_bound"] = data["source_high_water"]
        if "change_stream_position" not in data and "projector_checkpoint" in data:
            data["change_stream_position"] = data["projector_checkpoint"]
        if "projector_change_stream_position" not in data and "projector_checkpoint" in data:
            data["projector_change_stream_position"] = data["projector_checkpoint"]
        data.pop("source_high_water", None)
        data.pop("projector_checkpoint", None)
        return data

    @property
    def source_high_water(self) -> str | None:
        """Deprecated compatibility view; this is only the backfill bound."""

        return self.backfill_upper_bound

    @property
    def projector_checkpoint(self) -> str | None:
        """Deprecated compatibility view for the change-stream position."""

        return self.projector_change_stream_position


class RebuildLeaseStore(Protocol):
    async def acquire(self, record: RebuildRecord) -> bool: ...

    async def renew(self, record: RebuildRecord, lease_expires_at: datetime) -> bool: ...

    async def save(self, record: RebuildRecord) -> None: ...

    async def latest(self) -> RebuildRecord | None: ...

    async def get(self, rebuild_id: UUID) -> RebuildRecord | None: ...

    async def fencing_token(self, rebuild_id: UUID, owner: str) -> int | None: ...


class RebuildSearchPort(Protocol):
    async def resolve_alias(self, alias: str) -> str | None: ...

    async def create_index(self, index: str, definition: Mapping[str, object]) -> None: ...

    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int: ...

    async def count(self, index: str) -> int: ...

    def iter_event_ids(self, index: str) -> AsyncIterator[str]: ...

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None: ...

    async def delete_index(self, index: str) -> None: ...


class CanonicalEventSource(Protocol):
    async def capture_backfill_upper_bound(self) -> str | None: ...

    async def capture_high_water(self) -> str | None: ...

    def scan(self, *, backfill_upper_bound: str | None = None) -> AsyncIterator[CanonicalEvent]: ...


class RebuildConvergence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backfill_upper_bound: str | None = Field(default=None, max_length=256)
    # This is the source fence drained from an independent Mongo change
    # stream after backfill. It is never copied from a projector checkpoint.
    source_fence: str | None = Field(default=None, max_length=64)
    projector_change_stream_position: str | None = Field(default=None, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def migrate_boundary_names(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "backfill_upper_bound" not in data and "source_high_water" in data:
            data["backfill_upper_bound"] = data["source_high_water"]
        if "projector_change_stream_position" not in data and "projector_checkpoint" in data:
            data["projector_change_stream_position"] = data["projector_checkpoint"]
        data.pop("source_high_water", None)
        data.pop("projector_checkpoint", None)
        return data

    @property
    def source_high_water(self) -> str | None:
        return self.backfill_upper_bound

    @property
    def projector_checkpoint(self) -> str | None:
        return self.projector_change_stream_position


@dataclass(frozen=True, slots=True)
class RebuildBoundary:
    """Backfill query bound plus the projector marker at fence capture."""

    backfill_upper_bound: str | None
    change_stream_position: str | None


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=3, ge=1, le=10)
    delay_seconds: float = Field(default=0.1, ge=0, le=60)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SearchRebuilder:
    """Run a leased rebuild and swap only after target verification succeeds."""

    def __init__(
        self,
        *,
        state: RebuildLeaseStore,
        search: RebuildSearchPort,
        source: CanonicalEventSource,
        owner: str,
        source_collection: str = "events",
        alias: str = SEARCH_ALIAS,
        lease_duration: timedelta = timedelta(minutes=5),
        rollback_retention: timedelta = timedelta(hours=24),
        batch_size: int = 100,
        retry_policy: RetryPolicy | None = None,
        set_live_target: Callable[[str | None], Awaitable[None]] | None = None,
        capture_boundary: Callable[[], Awaitable[RebuildBoundary]] | None = None,
        wait_for_convergence: Callable[[RebuildBoundary], Awaitable[RebuildConvergence]]
        | None = None,
        before_verification: Callable[[str], Awaitable[None]] | None = None,
        now: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not owner or len(owner) > 128 or not 1 <= batch_size <= 10_000:
            raise ValueError("rebuild configuration is invalid")
        if lease_duration.total_seconds() <= 0 or rollback_retention.total_seconds() < 0:
            raise ValueError("rebuild durations are invalid")
        self._state = state
        self._search = search
        self._source = source
        self._owner = owner
        self._source_collection = source_collection
        self._alias = alias
        self._lease_duration = lease_duration
        self._rollback_retention = rollback_retention
        self._batch_size = batch_size
        self._retry_policy = retry_policy or RetryPolicy()
        self._set_live_target = set_live_target or _noop_target
        self._capture_boundary = capture_boundary
        self._wait_for_convergence = wait_for_convergence
        self._before_verification = before_verification
        self._now = now
        self._sleep = sleep
        self._alias_swapped = False

    async def run(self) -> RebuildRecord:
        started = self._now()
        rebuild_id = uuid4()
        old_index = await self._search.resolve_alias(self._alias)
        target_index = index_name(
            _next_prefix(old_index, self._alias), version=_next_version(old_index)
        )
        record = RebuildRecord(
            rebuild_id=rebuild_id,
            phase=RebuildPhase.ACQUIRING,
            started_at=started,
            source_collection=self._source_collection,
            old_index=old_index,
            target_index=target_index,
            owner=self._owner,
            lease_expires_at=started + self._lease_duration,
        )
        if not await self._state.acquire(record):
            raise RebuildError("rebuild_lease_unavailable", transient=True)
        fencing_token = getattr(self._state, "fencing_token", None)
        if callable(fencing_token):
            token = await fencing_token(record.rebuild_id, record.owner)
            if token is None:
                raise RebuildError("rebuild_lease_lost")
            record = record.model_copy(update={"fencing_token": token})
        live_target_active = False
        try:
            record = await self._transition(record, RebuildPhase.INDEX_CREATING)
            await self._search.create_index(target_index, INDEX_MAPPING)
            record = await self._transition(record, RebuildPhase.BULK_INDEXING)
            await self._set_live_target(target_index)
            live_target_active = True
            boundary = await self._capture_rebuild_boundary()
            if boundary is not None:
                try:
                    record = await self._save_update(
                        record.model_copy(
                            update={
                                "backfill_upper_bound": boundary.backfill_upper_bound,
                                "change_stream_position": boundary.change_stream_position,
                            }
                        )
                    )
                except Exception:
                    raise RebuildError("source_boundary_failed", transient=True) from None
            batch: list[Mapping[str, object]] = []
            scanned = 0
            indexed = 0
            failures: list[RebuildFailure] = []
            async for event in self._scan_source(record.backfill_upper_bound):
                scanned += 1
                batch.append(project_search_document(event))
                if len(batch) >= self._batch_size:
                    count, batch_failures = await self._bulk_with_retry(target_index, batch)
                    indexed += count
                    failures.extend(batch_failures)
                    batch = []
                    record = record.model_copy(
                        update={
                            "scanned_count": scanned,
                            "indexed_count": indexed,
                            "failure_count": len(failures),
                            "failures": tuple(failures[-32:]),
                        }
                    )
                    await self._state.save(record)
                    if not await self._renew_lease(record):
                        raise RebuildError("rebuild_lease_lost")
                    record = record.model_copy(
                        update={"lease_expires_at": self._now() + self._lease_duration}
                    )
                    self._emit(record, "search_rebuild.bulk_progress")
            if batch:
                count, batch_failures = await self._bulk_with_retry(target_index, batch)
                indexed += count
                failures.extend(batch_failures)
            record = record.model_copy(
                update={
                    "scanned_count": scanned,
                    "indexed_count": indexed,
                    "failure_count": len(failures),
                    "failures": tuple(failures[-32:]),
                }
            )
            record = await self._transition(record, RebuildPhase.RECONCILING)
            if self._wait_for_convergence is not None:
                try:
                    boundary = RebuildBoundary(
                        record.backfill_upper_bound, record.change_stream_position
                    )
                    try:
                        convergence = await self._wait_for_convergence(boundary)
                    except TypeError:
                        # Compatibility for pre-watermark test/application
                        # adapters; production wiring uses RebuildBoundary.
                        legacy_wait = cast(Any, self._wait_for_convergence)
                        convergence = await legacy_wait(boundary.backfill_upper_bound)
                except RebuildError:
                    raise
                except Exception:
                    raise RebuildError("projection_convergence_timeout", transient=True) from None
                record = await self._save_update(
                    record.model_copy(
                        update={
                            "backfill_upper_bound": convergence.backfill_upper_bound
                            or record.backfill_upper_bound,
                            "change_stream_position": (
                                convergence.source_fence or record.change_stream_position
                            ),
                            "projector_change_stream_position": (
                                convergence.projector_change_stream_position
                            ),
                        }
                    )
                )
            target_count = await self._search.count(target_index)
            record = await self._transition(record, RebuildPhase.VERIFYING)
            if self._before_verification is not None:
                await self._before_verification(target_index)
            identity_verified = await self._verify_identity(
                target_index, record.backfill_upper_bound
            )
            if failures or target_count < scanned or indexed != scanned or not identity_verified:
                raise RebuildError("rebuild_verification_failed")
            record = await self._transition(record, RebuildPhase.SWAPPING)
            await self._search.swap_alias(self._alias, old_index, target_index)
            self._alias_swapped = True
            completed = self._now()
            record = record.model_copy(
                update={
                    "phase": RebuildPhase.COMPLETED,
                    "completed_at": completed,
                    "rollback_until": completed + self._rollback_retention,
                }
            )
            try:
                await self._state.save(record)
            except Exception as error:
                # The alias commit is already durable. Preserve that fact in
                # the durable record when possible; generic failure cleanup
                # must never delete the newly serving generation.
                uncertain = record.model_copy(
                    update={
                        "phase": RebuildPhase.RECONCILIATION_REQUIRED,
                        "failures": tuple(
                            (*record.failures, RebuildFailure(code="rebuild_state_persist_failed"))
                        )[-32:],
                        "failure_count": record.failure_count + 1,
                    }
                )
                try:
                    await self._state.save(uncertain)
                except Exception as persist_error:
                    logger.error(
                        "post-swap rebuild state persistence failed",
                        extra={
                            "event": "search_rebuild.post_swap_state_persist_failed",
                            "error_type": type(persist_error).__name__,
                        },
                    )
                self._emit(uncertain, "search_rebuild.reconciliation_required")
                raise error
            self._emit(record, "search_rebuild.completed")
            return record
        except RebuildError as error:
            await self._record_failure(record, target_index, error.code)
            raise
        except Exception:
            await self._record_failure(record, target_index, "rebuild_unexpected_failure")
            raise
        finally:
            if live_target_active:
                try:
                    await self._set_live_target(None)
                except Exception as error:
                    logger.error(
                        "search rebuild live-target cleanup failed",
                        extra={
                            "event": "search_rebuild.live_target_cleanup_failed",
                            "error_type": type(error).__name__,
                        },
                    )

    async def _record_failure(
        self, record: RebuildRecord, target_index: str, failure_code: str
    ) -> None:
        if self._alias_swapped:
            # A committed alias cannot be rolled back by generic cleanup. The
            # durable state is explicitly uncertain until an operator resumes
            # or reconciles it.
            uncertain = record.model_copy(
                update={
                    "phase": RebuildPhase.RECONCILIATION_REQUIRED,
                    "completed_at": self._now(),
                    "failures": tuple((*record.failures, RebuildFailure(code=failure_code)))[-32:],
                    "failure_count": record.failure_count + 1,
                }
            )
            try:
                await self._state.save(uncertain)
            except Exception as error:
                logger.error(
                    "post-swap rebuild reconciliation persistence failed",
                    extra={
                        "event": "search_rebuild.reconciliation_state_persist_failed",
                        "error_type": type(error).__name__,
                    },
                )
            self._emit(uncertain, "search_rebuild.reconciliation_required")
            return
        failed = record.model_copy(
            update={
                "phase": RebuildPhase.FAILED,
                "completed_at": self._now(),
                "failures": tuple((*record.failures, RebuildFailure(code=failure_code))[-32:]),
                "failure_count": record.failure_count + 1,
            }
        )
        try:
            await self._state.save(failed)
        except Exception as error:
            logger.error(
                "search rebuild failure state persistence failed",
                extra={
                    "event": "search_rebuild.failure_state_persist_failed",
                    "error_type": type(error).__name__,
                },
            )
        self._emit(failed, "search_rebuild.failed")
        delete_index = getattr(self._search, "delete_index", None)
        if delete_index is None:
            return
        try:
            await delete_index(target_index)
        except Exception as error:
            logger.error(
                "search rebuild target cleanup failed",
                extra={
                    "event": "search_rebuild.cleanup_failed",
                    "error_type": type(error).__name__,
                },
            )

    async def _transition(self, record: RebuildRecord, phase: RebuildPhase) -> RebuildRecord:
        updated = record.model_copy(update={"phase": phase})
        await self._state.save(updated)
        self._emit(updated, f"search_rebuild.{phase.value}")
        return updated

    async def _save_update(self, record: RebuildRecord) -> RebuildRecord:
        await self._state.save(record)
        return record

    async def _verify_identity(self, target_index: str, high_water: str | None) -> bool:
        iterator = getattr(self._search, "iter_event_ids", None)
        if not callable(iterator):
            return True
        expected = self._scan_source(high_water)
        actual = iterator(target_index)
        expected_id = await anext(expected, None)
        actual_id = await anext(actual, None)
        while expected_id is not None:
            while actual_id is not None and actual_id < str(expected_id.event_id):
                actual_id = await anext(actual, None)
            if actual_id != str(expected_id.event_id):
                return False
            expected_id = await anext(expected, None)
        return True

    def _scan_source(self, backfill_upper_bound: str | None) -> AsyncIterator[CanonicalEvent]:
        try:
            return self._source.scan(backfill_upper_bound=backfill_upper_bound)
        except TypeError:
            # Preserve the small source protocol used by older test adapters;
            # production sources implement the explicit boundary argument.
            try:
                return self._source.scan(high_water=backfill_upper_bound)  # type: ignore[call-arg]
            except TypeError:
                return self._source.scan()

    async def _capture_rebuild_boundary(self) -> RebuildBoundary | None:
        if self._capture_boundary is not None:
            try:
                return await self._capture_boundary()
            except RebuildError:
                raise
            except Exception:
                raise RebuildError("source_boundary_failed", transient=True) from None
        capture_bound = getattr(self._source, "capture_backfill_upper_bound", None)
        if not callable(capture_bound):
            capture_bound = getattr(self._source, "capture_high_water", None)
        if not callable(capture_bound):
            return None
        try:
            return RebuildBoundary(await capture_bound(), None)
        except Exception:
            raise RebuildError("source_boundary_failed", transient=True) from None

    async def _renew_lease(self, record: RebuildRecord) -> bool:
        renew = getattr(self._state, "renew", None)
        if renew is None:
            return True
        expires = self._now() + self._lease_duration
        return bool(await renew(record, expires))

    async def _bulk_with_retry(
        self, target_index: str, batch: Sequence[Mapping[str, object]]
    ) -> tuple[int, list[RebuildFailure]]:
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                return await self._search.bulk_index(target_index, batch), []
            except RebuildError as error:
                if not error.transient or attempt == self._retry_policy.max_attempts:
                    return 0, [RebuildFailure(code=error.code)]
                await self._sleep(self._retry_policy.delay_seconds * attempt)
        return 0, [RebuildFailure(code="bulk_retry_exhausted")]

    @staticmethod
    def _emit(record: RebuildRecord, event: str) -> None:
        logger.info(
            event,
            extra={
                "event": event,
                "rebuild_id": str(record.rebuild_id),
                "phase": record.phase.value,
                "source_collection": record.source_collection,
                "old_index": record.old_index,
                "target_index": record.target_index,
                "scanned_count": record.scanned_count,
                "indexed_count": record.indexed_count,
                "failure_count": record.failure_count,
            },
        )


async def _noop_target(_target: str | None) -> None:
    return None


def _next_prefix(old_index: str | None, alias: str) -> str:
    if old_index and "-v" in old_index:
        return old_index.rsplit("-v", 1)[0]
    return alias


def _next_version(old_index: str | None) -> int:
    if old_index and "-v" in old_index:
        try:
            return int(old_index.rsplit("-v", 1)[1]) + 1
        except ValueError:
            pass
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or run a guarded Elasticsearch rebuild.")
    subparsers = parser.add_subparsers(dest="command")
    status = subparsers.add_parser("status", help="read the latest durable rebuild status")
    status.add_argument("--rebuild-id", help="optional rebuild ID to inspect")
    run = subparsers.add_parser("run", help="run a rebuild through the application harness")
    run.add_argument(
        "--confirm", action="store_true", help="required confirmation for a mutating rebuild"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run" and not args.confirm:
        raise SystemExit("refusing to run rebuild without --confirm")
    if args.command in {None, "status"}:
        if args.command is None:
            build_parser().print_help()
            return 0
        return asyncio.run(_status_command(args.rebuild_id))
    return asyncio.run(_run_command())


async def _run_command() -> int:
    """Run through the real Mongo, projector, and Elasticsearch graph."""

    try:
        settings = load_settings()
    except SettingsStartupError:
        logger.error(
            "rebuild run configuration failed",
            extra={"event": "search_rebuild.run_configuration_failed"},
        )
        return 2
    configure_logging(settings.log_level)
    if settings.mongo_url is None or settings.elasticsearch_url is None:
        logger.error(
            "rebuild run requires MongoDB and Elasticsearch",
            extra={
                "event": "search_rebuild.run_configuration_failed",
                "classification": "canonical_or_projection_dependency_missing",
            },
        )
        return 2
    from event_platform.search.rebuild_runtime import configured_rebuild_runtime

    try:
        async with configured_rebuild_runtime(settings) as rebuilder:
            record = await rebuilder.run()
    except RebuildError as error:
        logger.error(
            "search rebuild failed",
            extra={
                "event": "search_rebuild.run_failed",
                "failure_code": error.code,
                "transient": error.transient,
            },
        )
        return 1
    except Exception as error:
        logger.error(
            "search rebuild failed",
            extra={
                "event": "search_rebuild.run_failed",
                "error_type": type(error).__name__,
            },
        )
        return 1
    print(json.dumps(record.model_dump(mode="json"), sort_keys=True))
    return 0


async def _status_command(rebuild_id: str | None) -> int:
    """Print the latest durable status without requiring an application process."""

    try:
        settings = load_settings()
    except SettingsStartupError:
        logger.error(
            "rebuild status configuration failed",
            extra={"event": "search_rebuild.status_configuration_failed"},
        )
        return 2
    if settings.mongo_url is None:
        print(json.dumps({"status": "not_configured"}, sort_keys=True))
        return 0
    requested_id: UUID | None = None
    if rebuild_id is not None:
        try:
            requested_id = UUID(rebuild_id)
        except ValueError:
            logger.error(
                "rebuild status identifier is invalid",
                extra={"event": "search_rebuild.status_input_invalid"},
            )
            return 2
    from event_platform.storage.rebuilds import MongoRebuildStore

    client: AsyncMongoClient[Any] = AsyncMongoClient(settings.mongo_url)
    try:
        database = client[settings.mongo_database]
        store = MongoRebuildStore(database["search_rebuilds"], database["search_rebuild_leases"])
        record = await store.get(requested_id) if requested_id else await store.latest()
    except Exception as error:
        logger.error(
            "rebuild status lookup failed",
            extra={
                "event": "search_rebuild.status_lookup_failed",
                "error_type": type(error).__name__,
            },
        )
        return 1
    finally:
        await client.close()
    if record is None:
        print(json.dumps({"status": "not_found"}, sort_keys=True))
        return 0
    print(json.dumps(record.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
