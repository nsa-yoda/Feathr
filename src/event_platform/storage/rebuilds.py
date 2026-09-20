"""Mongo-backed durable rebuild lease and state storage."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError, PyMongoError

from event_platform.search.rebuild import RebuildLeaseStore, RebuildRecord


class RebuildStorageError(RuntimeError):
    """Safe Mongo rebuild-state dependency failure."""


class MongoRebuildStore(RebuildLeaseStore):
    _LOCK_ID = "__search_rebuild_lock__"

    def __init__(
        self,
        collection: AsyncCollection[Mapping[str, object]],
        lock_collection: AsyncCollection[Mapping[str, object]] | None = None,
    ) -> None:
        self._collection = collection
        # AsyncCollection intentionally rejects truth-value testing; use an
        # explicit None check while keeping the single-collection test adapter.
        self._lock_collection = lock_collection if lock_collection is not None else collection

    async def acquire(self, record: RebuildRecord) -> bool:
        now = datetime.now(UTC)
        try:
            lease_document = _document(record)
            lease_document.pop("fencing_token", None)
            document = await cast(Any, self._lock_collection).find_one_and_update(
                {
                    "_id": self._LOCK_ID,
                    "$or": [
                        {"phase": {"$in": ["completed", "failed"]}},
                        {"lease_expires_at": {"$lte": now}},
                        {"rebuild_id": {"$exists": False}},
                    ],
                },
                {"$set": lease_document, "$inc": {"fencing_token": 1}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return False
        except PyMongoError:
            raise RebuildStorageError("acquire_rebuild_lease") from None
        if not isinstance(document, Mapping) or document.get("rebuild_id") != str(
            record.rebuild_id
        ):
            return False
        token = document.get("fencing_token")
        if isinstance(token, int):
            record = record.model_copy(update={"fencing_token": token})
        try:
            await cast(Any, self._collection).replace_one(
                {"rebuild_id": str(record.rebuild_id)}, _document(record), upsert=True
            )
        except PyMongoError:
            raise RebuildStorageError("save_rebuild") from None
        return True

    async def renew(self, record: RebuildRecord, lease_expires_at: datetime) -> bool:
        try:
            result = await cast(Any, self._lock_collection).update_one(
                {
                    "_id": self._LOCK_ID,
                    "rebuild_id": str(record.rebuild_id),
                    "owner": record.owner,
                    "fencing_token": record.fencing_token,
                },
                {"$set": {"lease_expires_at": lease_expires_at}},
            )
        except PyMongoError:
            raise RebuildStorageError("renew_rebuild_lease") from None
        return bool(getattr(result, "modified_count", 0) or getattr(result, "matched_count", 0))

    async def save(self, record: RebuildRecord) -> None:
        try:
            result = await cast(Any, self._collection).replace_one(
                {
                    "rebuild_id": str(record.rebuild_id),
                    "owner": record.owner,
                    "fencing_token": record.fencing_token,
                },
                _document(record),
                upsert=False,
            )
            if getattr(result, "matched_count", 1) == 0:
                raise RebuildStorageError("rebuild_lease_lost")
            lock_result = await cast(Any, self._lock_collection).update_one(
                {
                    "_id": self._LOCK_ID,
                    "rebuild_id": str(record.rebuild_id),
                    "owner": record.owner,
                    "fencing_token": record.fencing_token,
                },
                {
                    "$set": {
                        "phase": record.phase.value,
                        "lease_expires_at": record.lease_expires_at,
                    }
                },
            )
            if getattr(lock_result, "matched_count", 1) == 0:
                raise RebuildStorageError("rebuild_lease_lost")
        except PyMongoError:
            raise RebuildStorageError("save_rebuild") from None

    async def fencing_token(self, rebuild_id: UUID, owner: str) -> int | None:
        """Read the current lease token so every state write is fenced."""

        try:
            document = await cast(Any, self._lock_collection).find_one(
                {
                    "_id": self._LOCK_ID,
                    "rebuild_id": str(rebuild_id),
                    "owner": owner,
                },
                projection={"fencing_token": 1},
            )
        except PyMongoError:
            raise RebuildStorageError("load_rebuild_lease") from None
        token = document.get("fencing_token") if isinstance(document, Mapping) else None
        return token if isinstance(token, int) and token >= 1 else None

    async def latest(self) -> RebuildRecord | None:
        try:
            document = await cast(Any, self._collection).find_one(
                {"_id": {"$ne": self._LOCK_ID}}, sort=[("started_at", -1)]
            )
        except PyMongoError:
            raise RebuildStorageError("load_rebuild") from None
        return _record(document) if document is not None else None

    async def get(self, rebuild_id: UUID) -> RebuildRecord | None:
        try:
            document = await cast(Any, self._collection).find_one(
                {"rebuild_id": str(rebuild_id), "_id": {"$ne": self._LOCK_ID}}
            )
        except PyMongoError:
            raise RebuildStorageError("load_rebuild") from None
        return _record(document) if document is not None else None


def _document(record: RebuildRecord) -> dict[str, object]:
    return record.model_dump(mode="json")


def _record(document: Mapping[str, object]) -> RebuildRecord:
    try:
        return RebuildRecord.model_validate(
            {key: value for key, value in document.items() if key != "_id"}
        )
    except (TypeError, ValueError, KeyError):
        raise RebuildStorageError("decode_rebuild") from None
