from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from bson import ObjectId
from elastic_transport import ApiError, TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.mapping import INDEX_MAPPING, index_name
from event_platform.search.projection import ProjectionStatus, SearchProjector
from event_platform.search.rebuild import (
    RebuildBoundary,
    RebuildConvergence,
    RebuildError,
    RebuildPhase,
    RebuildRecord,
    SearchRebuilder,
)
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.mongo import event_to_document
from event_platform.storage.projection_leases import MongoProjectionLeaseStore
from event_platform.storage.rebuild_source import MongoRebuildSource
from event_platform.storage.rebuilds import MongoRebuildStore
from tests.integration.support import (
    new_namespace,
    poll_until,
    require_elasticsearch,
    require_mongo,
)

pytestmark = [pytest.mark.integration, pytest.mark.acceptance]


def _event(label: str) -> CanonicalEvent:
    return CanonicalEvent.from_input(
        EventInput(
            event_type="view",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            user_id="integration-user",
            source_url=f"https://example.test/{label}",
            metadata={"term": label},
        ),
        event_id=uuid4(),
        ingested_at=datetime.now(UTC),
    )


async def _refresh_ids(es: AsyncElasticsearch, index: str, ids: set[UUID]) -> set[str]:
    await es.indices.refresh(index=index)
    response = await es.search(
        index=index,
        query={"ids": {"values": [str(event_id) for event_id in ids]}},
        size=len(ids) + 1,
        sort=[{"event_id": "asc"}],
    )
    hits = response.get("hits", {}).get("hits", [])
    return {
        str(hit.get("_id"))
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("_id"), str)
    }


async def _ids_ready(es: AsyncElasticsearch, index: str, ids: set[UUID]) -> set[str] | None:
    found = await _refresh_ids(es, index, ids)
    return found if found == {str(event_id) for event_id in ids} else None


async def _cleanup_indices(es: AsyncElasticsearch, suffix: str) -> None:
    try:
        indices = await es.indices.get(index=f"events-*{suffix}*")
    except ApiError as error:
        if getattr(getattr(error, "meta", None), "status", None) == 404:
            return
        raise
    if indices:
        await es.indices.delete(index=list(indices))


class PausedMongoSource:
    """Pause only the first backfill scan, creating a deterministic race window."""

    def __init__(self, collection: Any) -> None:
        self._source = MongoRebuildSource(collection)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.backfill_complete = asyncio.Event()
        self.after_backfill_release = asyncio.Event()
        self._scan_count = 0

    async def capture_high_water(self) -> str | None:
        return await self._source.capture_high_water()

    async def capture_backfill_upper_bound(self) -> str | None:
        return await self._source.capture_backfill_upper_bound()

    def scan(self, *, high_water: str | None = None) -> AsyncIterator[CanonicalEvent]:
        async def paused_scan() -> AsyncIterator[CanonicalEvent]:
            self._scan_count += 1
            if self._scan_count == 1:
                self.started.set()
                await self.release.wait()
            async for event in self._source.scan(high_water=high_water):
                yield event
            if self._scan_count == 1:
                self.backfill_complete.set()
                await self.after_backfill_release.wait()

        return paused_scan()


class ObservingAdapter(ElasticsearchRebuildAdapter):
    def __init__(self, client: AsyncElasticsearch) -> None:
        super().__init__(client)
        self.swap_calls: list[tuple[str | None, str, str | None]] = []

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
        before = await self.resolve_alias(alias)
        await super().swap_alias(alias, old_index, new_index)
        after = await self.resolve_alias(alias)
        self.swap_calls.append((before, new_index, after))


async def _wait_for_convergence(
    source: MongoRebuildSource | PausedMongoSource,
    projector: SearchProjector,
    boundary: RebuildBoundary,
    fence_holder: dict[str, object],
) -> RebuildConvergence:
    del source
    fence = fence_holder.pop("fence", None)
    latest = await cast(Any, fence).latest_position() if fence is not None else None
    target = latest
    if target is None:
        return RebuildConvergence(
            backfill_upper_bound=boundary.backfill_upper_bound,
            source_fence=latest,
            projector_change_stream_position=projector.change_stream_position(),
        )

    async def marker_ready() -> RebuildConvergence | None:
        marker = projector.change_stream_position()
        return (
            RebuildConvergence(
                backfill_upper_bound=boundary.backfill_upper_bound,
                source_fence=target,
                projector_change_stream_position=marker,
            )
            if marker is not None
            and tuple(map(int, marker.split(":", 1))) >= tuple(map(int, target.split(":", 1)))
            else None
        )

    return await poll_until(
        "projector candidate convergence",
        marker_ready,
        timeout_seconds=20,
        interval_seconds=0.05,
        observe=lambda _: {"checkpoint": projector.change_stream_position() is not None},
    )


async def _capture_boundary(
    source: MongoRebuildSource | PausedMongoSource,
    projector: SearchProjector,
    change_source: MongoChangeStreamSource,
    fence_holder: dict[str, object],
) -> RebuildBoundary:
    fence_holder["fence"] = await change_source.begin_fence()
    return RebuildBoundary(
        await source.capture_backfill_upper_bound(), projector.change_stream_position()
    )


async def _setup_projector(
    database: Any,
    events: Any,
    es: AsyncElasticsearch,
    alias: str,
    suffix: str,
) -> tuple[SearchProjector, asyncio.Task[ProjectionStatus], MongoProjectionLeaseStore]:
    checkpoint = MongoProjectionCheckpointStore(database["projection_checkpoints"])
    lease_store = MongoProjectionLeaseStore(database["projection_leases"])
    owner = f"integration-projector-{suffix}"
    projector = SearchProjector(
        projector="events-search",
        checkpoint=checkpoint,
        writer=ElasticsearchProjectionWriter(es, alias=alias),
        owner=owner,
    )
    lease = await lease_store.acquire(projector="events-search", owner=owner)
    assert lease is not None
    projector.set_ownership(owner=lease.owner, generation=lease.generation)
    ready = asyncio.Event()
    source = MongoChangeStreamSource(events, ready=ready)
    task = asyncio.create_task(projector.run_source(source))

    async def stream_ready() -> bool | None:
        return True if ready.is_set() else None

    await poll_until("projector change stream readiness", stream_ready, timeout_seconds=10)
    return projector, task, lease_store


@pytest.mark.asyncio
async def test_online_rebuild_proves_live_writes_convergence_and_atomic_cutover() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")
    await require_mongo(mongo_uri, require_replica_set=True)
    await require_elasticsearch(elasticsearch_url)
    mongo: AsyncMongoClient[Any] = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    namespace = new_namespace()
    database = mongo[namespace.database]
    events = database[namespace.collection]
    rebuilds = database[namespace.rebuild_collection]
    locks = database[namespace.lock_collection]
    alias = namespace.alias
    old_index = index_name(f"events-old-{namespace.suffix}")
    projector_task: asyncio.Task[ProjectionStatus] | None = None
    projector: SearchProjector | None = None
    try:
        await es.indices.create(
            index=old_index,
            settings=cast(dict[str, Any], INDEX_MAPPING["settings"]),
            mappings=cast(dict[str, Any], INDEX_MAPPING["mappings"]),
        )
        await es.indices.put_alias(index=old_index, name=alias)
        projector, projector_task, _ = await _setup_projector(
            database, events, es, alias, namespace.suffix
        )
        preallocated_event = _event("preallocated")
        preallocated_document = event_to_document(preallocated_event)
        preallocated_document["_id"] = ObjectId()
        seeds = [_event(label) for label in ("A", "B", "C")]
        await events.insert_many([event_to_document(event) for event in seeds])
        seed_ids = {event.event_id for event in seeds}
        await poll_until(
            "seed events through serving alias",
            lambda: _ids_ready(es, alias, seed_ids),
            timeout_seconds=20,
            interval_seconds=0.05,
            observe=lambda found: {"count": len(found or set())},
        )
        assert await ElasticsearchRebuildAdapter(es).resolve_alias(alias) == old_index

        source = PausedMongoSource(events)
        change_source = MongoChangeStreamSource(events)
        adapter = ObservingAdapter(es)
        target_history: list[str | None] = []
        fence_holder: dict[str, object] = {}

        async def set_live_target(target: str | None) -> None:
            target_history.append(target)
            assert projector is not None
            await projector.set_target_index(target)

        rebuilder = SearchRebuilder(
            state=MongoRebuildStore(rebuilds, lock_collection=locks),
            search=adapter,
            source=source,
            owner=f"integration-rebuild-{namespace.suffix}",
            alias=alias,
            source_collection=namespace.collection,
            batch_size=1,
            set_live_target=set_live_target,
            capture_boundary=lambda: _capture_boundary(
                source, projector, change_source, fence_holder
            ),
            wait_for_convergence=lambda boundary: _wait_for_convergence(
                source, projector, boundary, fence_holder
            ),
        )
        rebuild_task = asyncio.create_task(rebuilder.run())
        await asyncio.wait_for(source.started.wait(), timeout=10)
        current = await MongoRebuildStore(rebuilds, lock_collection=locks).latest()
        assert current is not None
        assert current.phase == RebuildPhase.BULK_INDEXING
        assert current.backfill_upper_bound is not None
        assert preallocated_document["_id"] < ObjectId(current.backfill_upper_bound)
        initial_projector_position = current.change_stream_position
        assert target_history == [current.target_index]

        live = [_event(label) for label in ("D", "E", "F")]
        live_events = [preallocated_event, *live]
        live_ids = {event.event_id for event in live_events}
        source.release.set()
        await asyncio.wait_for(source.backfill_complete.wait(), timeout=10)
        await events.insert_one(preallocated_document)
        await events.insert_many([event_to_document(event) for event in live])
        await poll_until(
            "live events dual-written to candidate",
            lambda: _ids_ready(es, current.target_index, live_ids),
            timeout_seconds=20,
            interval_seconds=0.05,
        )
        assert not rebuild_task.done()
        assert source.backfill_complete.is_set()
        source.after_backfill_release.set()
        result = await asyncio.wait_for(rebuild_task, timeout=30)
        assert result.phase == RebuildPhase.COMPLETED
        assert result.scanned_count == 3
        assert result.indexed_count == 3
        assert result.backfill_upper_bound is not None
        assert result.change_stream_position is not None
        assert result.change_stream_position != initial_projector_position
        assert result.projector_change_stream_position is not None
        assert tuple(map(int, result.projector_change_stream_position.split(":", 1))) >= tuple(
            map(int, result.change_stream_position.split(":", 1))
        )
        assert adapter.swap_calls == [(old_index, result.target_index, result.target_index)]
        assert target_history == [result.target_index, None]
        assert await adapter.resolve_alias(alias) == result.target_index
        all_ids = seed_ids | live_ids
        assert await _refresh_ids(es, alias, all_ids) == {str(event_id) for event_id in all_ids}

        post_cutover = _event("G")
        await events.insert_one(event_to_document(post_cutover))
        await poll_until(
            "post-cutover projection",
            lambda: _ids_ready(es, alias, {post_cutover.event_id}),
            timeout_seconds=20,
            interval_seconds=0.05,
        )
        assert await _refresh_ids(es, alias, all_ids | {post_cutover.event_id}) == {
            str(event_id) for event_id in all_ids | {post_cutover.event_id}
        }
        saved = await MongoRebuildStore(rebuilds, lock_collection=locks).get(result.rebuild_id)
        assert saved is not None
        assert saved.phase == RebuildPhase.COMPLETED
        assert saved.backfill_upper_bound == result.backfill_upper_bound
        aliases = await es.indices.get_alias(name=alias)
        assert list(aliases) == [result.target_index]
    finally:
        if projector is not None:
            projector.stop()
        if projector_task is not None:
            projector_task.cancel()
            await asyncio.gather(projector_task, return_exceptions=True)
        with suppress(ConnectionError, OSError, RuntimeError, TransportError):
            await _cleanup_indices(es, namespace.suffix)
        with suppress(ConnectionError, OSError, PyMongoError):
            await mongo.drop_database(namespace.database)
        with suppress(ConnectionError, OSError, RuntimeError, TransportError):
            await es.close()
        with suppress(ConnectionError, OSError, RuntimeError, PyMongoError):
            await mongo.close()


@pytest.mark.asyncio
async def test_online_rebuild_failure_boundaries_preserve_serving_generation() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")
    await require_mongo(mongo_uri, require_replica_set=True)
    await require_elasticsearch(elasticsearch_url)
    mongo: AsyncMongoClient[Any] = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    namespace = new_namespace()
    database = mongo[namespace.database]
    events = database[namespace.collection]
    seed = _event("failure")
    alias = namespace.alias
    old_index = index_name(f"events-old-{namespace.suffix}")
    try:
        await events.insert_one(event_to_document(seed))
        await es.indices.create(
            index=old_index,
            settings=cast(dict[str, Any], INDEX_MAPPING["settings"]),
            mappings=cast(dict[str, Any], INDEX_MAPPING["mappings"]),
        )
        await es.indices.put_alias(index=old_index, name=alias)
        state = MongoRebuildStore(database["rebuilds"], lock_collection=database["locks"])
        source = MongoRebuildSource(events)

        async def corrupt(target: str) -> None:
            await es.delete(index=target, id=str(seed.event_id))
            await es.indices.refresh(index=target)

        with pytest.raises(RebuildError, match="rebuild_verification_failed"):
            await SearchRebuilder(
                state=state,
                search=ElasticsearchRebuildAdapter(es),
                source=source,
                owner="verification-failure",
                alias=alias,
                before_verification=corrupt,
            ).run()
        assert await ElasticsearchRebuildAdapter(es).resolve_alias(alias) == old_index

        class FailingSwap(ElasticsearchRebuildAdapter):
            async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
                raise RebuildError("alias_swap_failed")

        swap_alias = f"{alias}-swap"
        swap_old_index = index_name(f"events-old-swap-{namespace.suffix}")
        await es.indices.create(
            index=swap_old_index,
            settings=cast(dict[str, Any], INDEX_MAPPING["settings"]),
            mappings=cast(dict[str, Any], INDEX_MAPPING["mappings"]),
        )
        await es.indices.put_alias(index=swap_old_index, name=swap_alias)
        swap_state = MongoRebuildStore(
            database["rebuilds_swap"], lock_collection=database["locks_swap"]
        )
        with pytest.raises(RebuildError, match="alias_swap_failed"):
            await SearchRebuilder(
                state=swap_state,
                search=FailingSwap(es),
                source=source,
                owner="swap-failure",
                alias=swap_alias,
            ).run()
        assert await ElasticsearchRebuildAdapter(es).resolve_alias(swap_alias) == swap_old_index

        post_alias = f"{alias}-post"
        post_old_index = index_name(f"events-old-post-{namespace.suffix}")
        await es.indices.create(
            index=post_old_index,
            settings=cast(dict[str, Any], INDEX_MAPPING["settings"]),
            mappings=cast(dict[str, Any], INDEX_MAPPING["mappings"]),
        )
        await es.indices.put_alias(index=post_old_index, name=post_alias)
        post_state_store = MongoRebuildStore(
            database["rebuilds_post"], lock_collection=database["locks_post"]
        )

        class FailingCompletedState:
            async def acquire(self, record: RebuildRecord) -> bool:
                return await post_state_store.acquire(record)

            async def fencing_token(self, rebuild_id: UUID, owner: str) -> int | None:
                return await post_state_store.fencing_token(rebuild_id, owner)

            async def renew(self, record: RebuildRecord, lease_expires_at: datetime) -> bool:
                return await post_state_store.renew(record, lease_expires_at)

            async def save(self, record: RebuildRecord) -> None:
                if record.phase == RebuildPhase.COMPLETED:
                    raise RuntimeError("injected post-swap persistence failure")
                await post_state_store.save(record)

            async def latest(self) -> RebuildRecord | None:
                return await post_state_store.latest()

            async def get(self, rebuild_id: UUID) -> RebuildRecord | None:
                return await post_state_store.get(rebuild_id)

        with pytest.raises(RuntimeError, match="post-swap persistence"):
            await SearchRebuilder(
                state=FailingCompletedState(),
                search=ElasticsearchRebuildAdapter(es),
                source=source,
                owner="post-swap-failure",
                alias=post_alias,
            ).run()
        promoted = await ElasticsearchRebuildAdapter(es).resolve_alias(post_alias)
        assert promoted is not None and promoted != post_old_index
        assert await es.indices.exists(index=promoted)
        uncertain = await post_state_store.latest()
        assert uncertain is not None
        assert uncertain.phase == RebuildPhase.RECONCILIATION_REQUIRED
    finally:
        with suppress(ConnectionError, OSError, RuntimeError, TransportError):
            await _cleanup_indices(es, namespace.suffix)
        with suppress(ConnectionError, OSError, PyMongoError):
            await mongo.drop_database(namespace.database)
        with suppress(ConnectionError, OSError, RuntimeError, TransportError):
            await es.close()
        with suppress(ConnectionError, OSError, RuntimeError, PyMongoError):
            await mongo.close()
