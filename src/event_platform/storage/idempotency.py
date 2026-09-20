"""Durable request idempotency with owner-fenced state transitions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import DuplicateKeyError, PyMongoError


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    outcome: str
    event_id: UUID
    reservation_token: str | None = None
    generation: int | None = None


class IdempotencyRegistryError(RuntimeError):
    """Safe dependency failure for the idempotency boundary."""


class IdempotencyRegistry(Protocol):
    async def reserve(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        fingerprint: str,
        event_id: UUID,
        now: datetime,
        replay_window: timedelta,
    ) -> IdempotencyDecision: ...

    async def complete(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None: ...

    async def release(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None: ...


def registry_id(scope: str, key: str, operation: str) -> str:
    return hashlib.sha256(f"{scope}\x00{operation}\x00{key}".encode()).hexdigest()


def _new_token() -> str:
    return uuid4().hex


class InMemoryIdempotencyRegistry:
    """Single-process adapter with the same owner-fenced contract as Mongo."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, object]] = {}

    async def reserve(self, **kwargs: object) -> IdempotencyDecision:
        now = kwargs["now"]
        replay_window = kwargs["replay_window"]
        if not isinstance(now, datetime) or not isinstance(replay_window, timedelta):
            raise TypeError("invalid idempotency timing")
        identifier = registry_id(str(kwargs["scope"]), str(kwargs["key"]), str(kwargs["operation"]))
        event_id = kwargs["event_id"]
        if not isinstance(event_id, UUID):
            raise TypeError("event_id must be UUID")
        fingerprint = kwargs["fingerprint"]
        existing = self._records.get(identifier)
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                return IdempotencyDecision("conflict", event_id)
            stored_event = UUID(str(existing["event_id"]))
            if existing["status"] in {"completed", "enqueued"}:
                return IdempotencyDecision("replay", stored_event)
            created_at = existing["created_at"]
            if isinstance(created_at, datetime) and now - created_at < replay_window:
                return IdempotencyDecision("in_flight", stored_event)
            existing_generation = existing.get("generation", 1)
            generation = (existing_generation if isinstance(existing_generation, int) else 1) + 1
        else:
            generation = 1
        token = _new_token()
        self._records[identifier] = {
            "fingerprint": fingerprint,
            "event_id": str(event_id),
            "status": "reserved",
            "created_at": now,
            "reservation_token": token,
            "generation": generation,
        }
        return IdempotencyDecision("new", event_id, token, generation)

    async def complete(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None:
        record = self._records.get(registry_id(scope, key, operation))
        if record is None or record["event_id"] != str(event_id):
            return
        if reservation_token is not None and record.get("reservation_token") != reservation_token:
            return
        record["status"] = "enqueued"
        record["enqueued_at"] = datetime.now(UTC)

    async def release(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None:
        identifier = registry_id(scope, key, operation)
        record = self._records.get(identifier)
        if record is None or record["event_id"] != str(event_id):
            return
        if reservation_token is not None and record.get("reservation_token") != reservation_token:
            return
        if record.get("status") == "reserved":
            self._records.pop(identifier, None)


class MongoIdempotencyRegistry:
    def __init__(self, collection: AsyncCollection[dict[str, object]]) -> None:
        self._collection = collection

    async def reserve(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        fingerprint: str,
        event_id: UUID,
        now: datetime,
        replay_window: timedelta,
    ) -> IdempotencyDecision:
        identifier = registry_id(scope, key, operation)
        token = _new_token()
        try:
            document = await self._collection.find_one({"_id": identifier})
            if document is None:
                await self._collection.insert_one(
                    {
                        "_id": identifier,
                        "scope": scope,
                        "operation": operation,
                        "fingerprint": fingerprint,
                        "event_id": str(event_id),
                        "status": "reserved",
                        "created_at": now,
                        "reservation_token": token,
                        "generation": 1,
                    }
                )
                return IdempotencyDecision("new", event_id, token, 1)
        except DuplicateKeyError:
            document = await self._collection.find_one({"_id": identifier})
        except PyMongoError:
            raise IdempotencyRegistryError("reserve_idempotency") from None
        if not isinstance(document, dict):
            raise IdempotencyRegistryError("reserve_idempotency")
        if document.get("fingerprint") != fingerprint:
            return IdempotencyDecision("conflict", event_id)
        stored_event = UUID(str(document.get("event_id")))
        if document.get("status") in {"completed", "enqueued"}:
            return IdempotencyDecision("replay", stored_event)
        created_at = document.get("created_at")
        if isinstance(created_at, datetime) and now - created_at < replay_window:
            return IdempotencyDecision("in_flight", stored_event)

        observed_token = document.get("reservation_token")
        observed_generation = document.get("generation", 1)
        if not isinstance(observed_token, str) or not isinstance(observed_generation, int):
            raise IdempotencyRegistryError("reserve_idempotency")
        try:
            replacement = await self._collection.find_one_and_update(
                {
                    "_id": identifier,
                    "fingerprint": fingerprint,
                    "status": "reserved",
                    "reservation_token": observed_token,
                    "generation": observed_generation,
                    "created_at": created_at,
                },
                {
                    "$set": {
                        "event_id": str(event_id),
                        "created_at": now,
                        "status": "reserved",
                        "reservation_token": token,
                    },
                    "$inc": {"generation": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError:
            raise IdempotencyRegistryError("reserve_idempotency") from None
        if not isinstance(replacement, dict) or replacement.get("reservation_token") != token:
            return IdempotencyDecision("in_flight", stored_event)
        replacement_generation = replacement.get("generation", 1)
        if not isinstance(replacement_generation, int):
            raise IdempotencyRegistryError("reserve_idempotency")
        return IdempotencyDecision("new", event_id, token, replacement_generation)

    async def complete(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None:
        query: dict[str, object] = {
            "_id": registry_id(scope, key, operation),
            "event_id": str(event_id),
            "status": "reserved",
        }
        if reservation_token is not None:
            query["reservation_token"] = reservation_token
        try:
            await self._collection.update_one(
                query,
                {"$set": {"status": "enqueued", "enqueued_at": datetime.now(UTC)}},
            )
        except PyMongoError:
            raise IdempotencyRegistryError("complete_idempotency") from None

    async def release(
        self,
        *,
        scope: str,
        key: str,
        operation: str,
        event_id: UUID,
        reservation_token: str | None = None,
    ) -> None:
        query: dict[str, object] = {
            "_id": registry_id(scope, key, operation),
            "event_id": str(event_id),
            "status": "reserved",
        }
        if reservation_token is not None:
            query["reservation_token"] = reservation_token
        try:
            await self._collection.delete_one(query)
        except PyMongoError:
            raise IdempotencyRegistryError("release_idempotency") from None
