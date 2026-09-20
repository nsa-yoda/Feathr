"""Canonical Mongo source and high-water boundary for online rebuilds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from event_platform.domain.events import CanonicalEvent
from event_platform.storage.mongo import event_from_document


class MongoRebuildSource:
    """Read canonical events through a durable Mongo ObjectId boundary.

    Mongo's generated ``_id`` is monotonic for the insertion stream used by the
    single replica-set deployment. The boundary is persisted as its hex value;
    backfill reads only documents at or below it while the live change stream
    handles later inserts.
    """

    def __init__(self, collection: AsyncCollection[Mapping[str, object]]) -> None:
        self._collection = collection

    async def capture_high_water(self) -> str | None:
        document = await self._collection.find_one({}, projection={"_id": 1}, sort=[("_id", -1)])
        if document is None:
            return None
        value = document.get("_id")
        if not isinstance(value, ObjectId):
            raise ValueError("canonical Mongo identifier is not an ObjectId")
        return str(value)

    def scan(self, *, high_water: str | None = None) -> AsyncIterator[CanonicalEvent]:
        async def events() -> AsyncIterator[CanonicalEvent]:
            query: dict[str, object] = {}
            if high_water is not None:
                query["_id"] = {"$lte": ObjectId(high_water)}
            cursor = self._collection.find(query).sort("event_id", 1)
            async for document in cursor:
                yield event_from_document(document)

        return events()
