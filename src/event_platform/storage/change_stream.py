"""Async insert-only Mongo change-stream source."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

from bson.timestamp import Timestamp
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import PyMongoError

from event_platform.search.projection import (
    ChangeStreamEvent,
    InvalidResumeHistory,
    MalformedChange,
    ProjectionError,
)
from event_platform.storage.mongo import MongoDependencyError, event_from_document


class MongoChangeStreamSource:
    def __init__(
        self,
        collection: AsyncCollection[Mapping[str, object]],
        *,
        ready: asyncio.Event | None = None,
    ) -> None:
        self._collection = collection
        self._ready = ready

    async def stream(
        self, *, resume_after: Mapping[str, object] | None = None
    ) -> AsyncIterator[ChangeStreamEvent]:
        try:
            pipeline = [{"$match": {"operationType": "insert"}}]
            if resume_after is None:
                stream = await self._collection.watch(pipeline, full_document="default")
            else:
                stream = await self._collection.watch(
                    pipeline,
                    full_document="default",
                    resume_after=dict(resume_after),
                )
            if self._ready is not None:
                self._ready.set()
            async with stream:
                async for change in stream:
                    yield _decode_change(change)
        except PyMongoError as error:
            if _is_invalid_resume(error):
                raise InvalidResumeHistory() from None
            raise ProjectionError("dependency_unavailable", transient=True) from None

    async def latest_position(self, *, resume_after: Mapping[str, object] | None) -> str | None:
        """Drain currently available changes and return their last operation time.

        The stream is independent from the live projector, so this does not
        consume its cursor. ``try_next`` performs one bounded getMore and
        returns ``None`` when the current stream position has been reached.
        The returned cluster time is an ordered change-stream watermark; the
        raw resume token remains the projector's durable restart cursor.
        """

        try:
            pipeline = [{"$match": {"operationType": "insert"}}]
            stream = await self._collection.watch(
                pipeline,
                full_document="default",
                resume_after=dict(resume_after) if resume_after is not None else None,
                max_await_time_ms=0,
            )
            latest: str | None = None
            async with stream:
                while True:
                    change = await stream.try_next()
                    if change is None:
                        return latest
                    latest = _cluster_time(change.get("clusterTime")) or latest
        except PyMongoError as error:
            if _is_invalid_resume(error):
                raise InvalidResumeHistory() from None
            raise ProjectionError("dependency_unavailable", transient=True) from None

    async def begin_fence(self) -> MongoChangeStreamFence:
        """Open an independent source-progress cursor for an online rebuild.

        The cursor starts at Mongo's current logical operation time and is kept
        open while the bounded ObjectId backfill runs.  Draining it afterwards
        yields the latest ordered ``clusterTime`` for inserts committed during
        the rebuild window.  It never reads or derives its fence from the
        projector's persisted resume token.
        """

        try:
            operation_time = await _current_operation_time(self._collection)
            pipeline = [{"$match": {"operationType": "insert"}}]
            kwargs: dict[str, object] = {
                "full_document": "default",
                # A short bounded getMore lets Mongo deliver commits that
                # occurred while the backfill cursor was active.
                "max_await_time_ms": 1_000,
            }
            if operation_time is not None:
                kwargs["start_at_operation_time"] = operation_time
            watch = cast(Any, self._collection.watch)
            stream = await watch(pipeline, **kwargs)
            return MongoChangeStreamFence(stream)
        except PyMongoError as error:
            if _is_invalid_resume(error):
                raise InvalidResumeHistory() from None
            raise ProjectionError("dependency_unavailable", transient=True) from None


def _decode_change(change: Mapping[str, object]) -> ChangeStreamEvent:
    token = change.get("_id")
    document = change.get("fullDocument")
    if change.get("operationType") != "insert":
        raise MalformedChange()
    if not isinstance(token, Mapping) or not isinstance(document, Mapping):
        raise MalformedChange()
    try:
        source_id = document.get("_id")
        event_object_id = str(source_id) if source_id is not None else None
        return ChangeStreamEvent(
            dict(token),
            event_from_document(document),
            event_object_id,
            _cluster_time(change.get("clusterTime")),
        )
    except (KeyError, TypeError, ValueError, MongoDependencyError):
        raise MalformedChange() from None


def _is_invalid_resume(error: PyMongoError) -> bool:
    code = getattr(error, "code", None)
    return code in {260, 286} or "resume" in str(error).lower() or "history" in str(error).lower()


def _cluster_time(value: object) -> str | None:
    if not isinstance(value, Timestamp):
        return None
    return f"{value.time}:{value.inc}"


@dataclass(slots=True)
class MongoChangeStreamFence:
    """A bounded, independent Mongo source-progress observation."""

    _stream: Any

    async def latest_position(self) -> str | None:
        latest: str | None = None
        try:
            while True:
                change = await self._stream.try_next()
                if change is None:
                    return latest
                latest = _cluster_time(change.get("clusterTime")) or latest
        except PyMongoError as error:
            if _is_invalid_resume(error):
                raise InvalidResumeHistory() from None
            raise ProjectionError("dependency_unavailable", transient=True) from None
        finally:
            await self.close()

    async def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is None:
            return
        result = close()
        if hasattr(result, "__await__"):
            await result


async def _current_operation_time(
    collection: AsyncCollection[Mapping[str, object]],
) -> Timestamp | None:
    database = getattr(collection, "database", None)
    client = getattr(database, "client", None)
    admin = getattr(client, "admin", None)
    command = getattr(admin, "command", None)
    if not callable(command):
        return None
    hello = await command("hello")
    cluster_time = hello.get("$clusterTime", {}).get("clusterTime")
    return cluster_time if isinstance(cluster_time, Timestamp) else None
