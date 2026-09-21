from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError

from event_platform.storage.projection_leases import MongoProjectionLeaseStore, ProjectionLeaseError

pytestmark = pytest.mark.unit


class Result:
    matched_count = 1


class LeaseCollection:
    def __init__(self) -> None:
        self.document: dict[str, object] | None = None

    async def find_one(self, _query: Mapping[str, object]) -> dict[str, object] | None:
        return self.document

    async def find_one_and_update(
        self, query: Mapping[str, object], update: Mapping[str, object], **_: object
    ) -> dict[str, object] | None:
        if self.document is not None:
            if "owner" in query:
                if self.document.get("owner") != query.get("owner") or self.document.get(
                    "generation"
                ) != query.get("generation"):
                    return None
                increment = update.get("$inc", {}).get("generation", 0)  # type: ignore[union-attr]
                self.document["generation"] = int(self.document["generation"]) + int(increment)  # type: ignore[arg-type]
                return self.document
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
        on_insert = update.get("$setOnInsert", {})
        increments = update.get("$inc", {"generation": 0})
        inserted_generation = update.get("$setOnInsert", {}).get("generation", 0)  # type: ignore[union-attr]
        self.document = {
            "_id": query["_id"],
            **(self.document or {}),
            **(on_insert if self.document is None else {}),  # type: ignore[arg-type]
            **values,  # type: ignore[arg-type]
            "generation": int((self.document or {}).get("generation", inserted_generation))
            + int(increments["generation"]),  # type: ignore[index]
        }
        return self.document

    async def update_one(self, query: Mapping[str, object], update: Mapping[str, object]) -> Result:
        if self.document is None or self.document.get("owner") != query.get("owner"):
            return type("NoMatch", (), {"matched_count": 0})()
        self.document.update(update["$set"])  # type: ignore[arg-type]
        return Result()


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


@pytest.mark.asyncio
async def test_release_keeps_fencing_generation_and_checkpoint_floor_is_honored() -> None:
    collection = LeaseCollection()
    store = MongoProjectionLeaseStore(collection)  # type: ignore[arg-type]
    first = await store.acquire(projector="events-search", owner="one")
    assert first is not None and first.generation == 1
    await store.release(first)
    second = await store.acquire(projector="events-search", owner="two")
    assert second is not None and second.generation == 2

    legacy = LeaseCollection()
    legacy_store = MongoProjectionLeaseStore(legacy)  # type: ignore[arg-type]
    recovered = await legacy_store.acquire(
        projector="events-search", owner="new-owner", minimum_generation=7
    )
    assert recovered is not None and recovered.generation == 8


@pytest.mark.asyncio
async def test_projection_lease_rejects_invalid_arguments_and_duplicate_races() -> None:
    store = MongoProjectionLeaseStore(LeaseCollection())  # type: ignore[arg-type]
    for kwargs in (
        {"projector": "", "owner": "owner"},
        {"projector": "events-search", "owner": ""},
        {"projector": "events-search", "owner": "owner", "lease_seconds": 0},
        {"projector": "events-search", "owner": "owner", "minimum_generation": -1},
    ):
        with pytest.raises(ValueError, match="projection lease arguments"):
            await store.acquire(**kwargs)

    class Duplicate:
        async def find_one(self, _query: object) -> None:
            return None

        async def find_one_and_update(self, *_args: object, **_kwargs: object) -> None:
            raise DuplicateKeyError("concurrent insert")

    assert (
        await MongoProjectionLeaseStore(Duplicate()).acquire(
            projector="events-search", owner="owner"
        )
        is None
    )


@pytest.mark.asyncio
async def test_projection_lease_classifies_decode_and_fencing_update_failures() -> None:
    class InvalidDocument:
        async def find_one(self, _query: object) -> Mapping[str, object]:
            return {"owner": "owner", "generation": "invalid"}

        async def find_one_and_update(
            self, *_args: object, **_kwargs: object
        ) -> Mapping[str, object]:
            return {"owner": "owner", "generation": "invalid"}

    with pytest.raises(ProjectionLeaseError, match="decode_projection_lease"):
        await MongoProjectionLeaseStore(InvalidDocument()).acquire(  # type: ignore[arg-type]
            projector="events-search", owner="owner"
        )

    class FailingFloorUpdate:
        async def find_one(self, _query: object) -> Mapping[str, object]:
            return {"owner": "owner", "generation": 1}

        def __init__(self) -> None:
            self.calls = 0

        async def find_one_and_update(
            self, *_args: object, **_kwargs: object
        ) -> Mapping[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"owner": "owner", "generation": 1}
            raise PyMongoError("checkpoint floor race")

    with pytest.raises(ProjectionLeaseError, match="acquire_projection_lease"):
        await MongoProjectionLeaseStore(FailingFloorUpdate()).acquire(  # type: ignore[arg-type]
            projector="events-search", owner="owner", minimum_generation=7
        )
