from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from event_platform.storage.projection_leases import MongoProjectionLeaseStore

pytestmark = pytest.mark.unit


class Result:
    matched_count = 1


class LeaseCollection:
    def __init__(self) -> None:
        self.document: dict[str, object] | None = None

    async def find_one_and_update(
        self, query: Mapping[str, object], update: Mapping[str, object], **_: object
    ) -> dict[str, object] | None:
        if self.document is not None:
            owner = self.document.get("owner")
            expires = self.document.get("lease_expires_at")
            allowed = (
                owner == query["$or"][1]["owner"]  # type: ignore[index]
                or not isinstance(expires, datetime)
                or expires <= query["$or"][0]["lease_expires_at"]["$lte"]  # type: ignore[index]
            )
            if not allowed:
                return None
        values = update["$set"]
        increments = update["$inc"]
        self.document = {
            "_id": query["_id"],
            **(self.document or {}),
            **values,  # type: ignore[arg-type]
            "generation": int((self.document or {}).get("generation", 0))
            + int(increments["generation"]),  # type: ignore[index]
        }
        return self.document

    async def update_one(self, query: Mapping[str, object], update: Mapping[str, object]) -> Result:
        if self.document is None or self.document.get("owner") != query.get("owner"):
            return type("NoMatch", (), {"matched_count": 0})()
        self.document.update(update["$set"])  # type: ignore[arg-type]
        return Result()

    async def delete_one(self, _query: Mapping[str, object]) -> None:
        self.document = None


@pytest.mark.asyncio
async def test_projection_lease_takeover_and_stale_renewal_are_fenced() -> None:
    collection = LeaseCollection()
    store = MongoProjectionLeaseStore(collection)  # type: ignore[arg-type]
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = await store.acquire(projector="events-search", owner="one", now=now)
    assert first is not None and first.generation == 1
    assert await store.acquire(projector="events-search", owner="two", now=now) is None
    second = await store.acquire(
        projector="events-search", owner="two", now=now + timedelta(seconds=31)
    )
    assert second is not None and second.generation == 2
    assert await store.renew(first, now=now + timedelta(seconds=32)) is None
    assert await store.renew(second, now=now + timedelta(seconds=32)) is not None
