"""Async insert-only Mongo change-stream source."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

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


def _decode_change(change: Mapping[str, object]) -> ChangeStreamEvent:
    token = change.get("_id")
    document = change.get("fullDocument")
    if change.get("operationType") != "insert":
        raise MalformedChange()
    if not isinstance(token, Mapping) or not isinstance(document, Mapping):
        raise MalformedChange()
    try:
        return ChangeStreamEvent(dict(token), event_from_document(document))
    except (KeyError, TypeError, ValueError, MongoDependencyError):
        raise MalformedChange() from None


def _is_invalid_resume(error: PyMongoError) -> bool:
    code = getattr(error, "code", None)
    return code in {260, 286} or "resume" in str(error).lower() or "history" in str(error).lower()
