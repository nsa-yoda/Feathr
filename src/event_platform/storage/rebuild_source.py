"""Canonical Mongo source and bounded backfill boundary for online rebuilds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.read_concern import ReadConcern

from event_platform.domain.events import CanonicalEvent
from event_platform.storage.mongo import event_from_document


class MongoRebuildSource:
    """Read canonical events through a majority-consistent ObjectId bound."""

    def __init__(self, collection: AsyncCollection[Mapping[str, object]]) -> None:
        self._collection = collection

    async def capture_backfill_upper_bound(self) -> str | None:
        # This is a scan optimization only. A change-stream position, not this
        # ObjectId, proves that concurrent writes have been observed.
        with_options = getattr(self._collection, "with_options", None)
        collection = (
            with_options(read_concern=ReadConcern("majority"))
            if callable(with_options)
            else self._collection
        )
        document = await collection.find_one({}, projection={"_id": 1}, sort=[("_id", -1)])
        if document is None:
            return None
        value = document.get("_id")
        if not isinstance(value, ObjectId):
            raise ValueError("canonical Mongo identifier is not an ObjectId")
        return str(value)

    async def capture_high_water(self) -> str | None:
        """Compatibility alias for callers migrating to the explicit name."""

        return await self.capture_backfill_upper_bound()

    def scan(
        self,
        *,
        backfill_upper_bound: str | None = None,
        high_water: str | None = None,
    ) -> AsyncIterator[CanonicalEvent]:
        async def events() -> AsyncIterator[CanonicalEvent]:
            query: dict[str, object] = {}
            bound = backfill_upper_bound if backfill_upper_bound is not None else high_water
            if bound is not None:
                query["_id"] = {"$lte": ObjectId(bound)}
            with_options = getattr(self._collection, "with_options", None)
            collection = (
                with_options(read_concern=ReadConcern("majority"))
                if callable(with_options)
                else self._collection
            )
            cursor = collection.find(query).sort("event_id", 1)
            async for document in cursor:
                yield event_from_document(document)

        return events()
