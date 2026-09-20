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
    ) -> ProjectionLease | None:
        if not projector or not owner or lease_seconds <= 0:
            raise ValueError("projection lease arguments are invalid")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        expires_at = current + timedelta(seconds=lease_seconds)
        try:
            document = await cast(Any, self._collection).find_one_and_update(
                {
                    "_id": projector,
                    "$or": [
                        {"lease_expires_at": {"$lte": current}},
                        {"owner": owner},
                        {"lease_expires_at": {"$exists": False}},
                    ],
                },
                {
                    "$set": {
                        "projector": projector,
                        "owner": owner,
                        "lease_expires_at": expires_at,
                        "renewed_at": current,
                    },
                    "$inc": {"generation": 1},
                },
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
        try:
            await cast(Any, self._collection).delete_one(
                {
                    "_id": lease.projector,
                    "owner": lease.owner,
                    "generation": lease.generation,
                }
            )
        except PyMongoError:
            raise ProjectionLeaseError("release_projection_lease") from None
