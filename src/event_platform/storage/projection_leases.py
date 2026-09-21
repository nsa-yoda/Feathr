"""Mongo-backed projector leases with fencing generations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError, PyMongoError


class ProjectionLeaseError(RuntimeError):
    """Safe projector ownership dependency failure."""


@dataclass(frozen=True, slots=True)
class ProjectionLease:
    projector: str
    owner: str
    generation: int
    expires_at: datetime


class MongoProjectionLeaseStore:
    def __init__(self, collection: AsyncCollection[Mapping[str, object]]) -> None:
        self._collection = collection

    async def acquire(
        self,
        *,
        projector: str,
        owner: str,
        lease_seconds: float = 30.0,
        now: datetime | None = None,
        minimum_generation: int = 0,
    ) -> ProjectionLease | None:
        if not projector or not owner or lease_seconds <= 0 or minimum_generation < 0:
            raise ValueError("projection lease arguments are invalid")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = current + timedelta(seconds=lease_seconds)
        try:
            existing = await cast(Any, self._collection).find_one({"_id": projector})
            update: dict[str, object] = {
                "$set": {
                    "projector": projector,
                    "owner": owner,
                    "lease_expires_at": expires_at,
                    "renewed_at": current,
                }
            }
            if existing is None:
                # $setOnInsert and $inc cannot address the same path in one
                # Mongo update.  A missing record is a new generation, while
                # an existing record is advanced atomically below.
                update["$setOnInsert"] = {"generation": minimum_generation + 1}
            else:
                update["$inc"] = {"generation": 1}
            document = await cast(Any, self._collection).find_one_and_update(
                {
                    "_id": projector,
                    "$or": [
                        {"lease_expires_at": {"$lte": current}},
                        {"owner": owner},
                        {"lease_expires_at": {"$exists": False}},
                    ],
                },
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return None
        except PyMongoError:
            raise ProjectionLeaseError("acquire_projection_lease") from None
        if not isinstance(document, Mapping) or document.get("owner") != owner:
            return None
        generation = document.get("generation")
        if not isinstance(generation, int) or generation < 1:
            raise ProjectionLeaseError("decode_projection_lease")
        # A legacy deployment deleted the lease record on release.  If a
        # checkpoint survived that deletion, initialize this newly-created
        # lease above the checkpoint generation before allowing it to write.
        if generation <= minimum_generation:
            try:
                document = await cast(Any, self._collection).find_one_and_update(
                    {
                        "_id": projector,
                        "owner": owner,
                        "generation": generation,
                    },
                    {"$inc": {"generation": minimum_generation - generation + 1}},
                    return_document=ReturnDocument.AFTER,
                )
            except PyMongoError:
                raise ProjectionLeaseError("acquire_projection_lease") from None
            if not isinstance(document, Mapping) or document.get("owner") != owner:
                return None
            generation = document.get("generation")
            if not isinstance(generation, int) or generation <= minimum_generation:
                raise ProjectionLeaseError("decode_projection_lease")
        return ProjectionLease(projector, owner, generation, expires_at)

    async def renew(
        self,
        lease: ProjectionLease,
        *,
        lease_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> ProjectionLease | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = current + timedelta(seconds=lease_seconds)
        try:
            result = await cast(Any, self._collection).update_one(
                {
                    "_id": lease.projector,
                    "owner": lease.owner,
                    "generation": lease.generation,
                    "lease_expires_at": {"$gt": current},
                },
                {"$set": {"lease_expires_at": expires_at, "renewed_at": current}},
            )
        except PyMongoError:
            raise ProjectionLeaseError("renew_projection_lease") from None
        if not getattr(result, "matched_count", 0):
            return None
        return ProjectionLease(lease.projector, lease.owner, lease.generation, expires_at)

    async def release(self, lease: ProjectionLease) -> None:
        """Expire a lease while retaining its fencing generation.

        Deleting the record lets a later process reuse the same generation
        while an older checkpoint still carries it.  Keeping an expired
        tombstone makes every subsequent acquisition strictly newer.
        """

        try:
            result = await cast(Any, self._collection).update_one(
                {
                    "_id": lease.projector,
                    "owner": lease.owner,
                    "generation": lease.generation,
                },
                {
                    "$set": {
                        "lease_expires_at": datetime.now(UTC),
                        "released_at": datetime.now(UTC),
                    }
                },
            )
            # A stale owner has already lost the lease; there is nothing to
            # release and, critically, no state to remove.
            del result
        except PyMongoError:
            raise ProjectionLeaseError("release_projection_lease") from None
