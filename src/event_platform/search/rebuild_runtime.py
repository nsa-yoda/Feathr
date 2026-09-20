"""Application dependency graph for an executable online search rebuild."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient

from event_platform.core.settings import ServiceSettings
from event_platform.search.bootstrap import ensure_search_alias
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter, create_client
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.projection import SearchProjector
from event_platform.search.rebuild import (
    RebuildBoundary,
    RebuildConvergence,
    RebuildError,
    SearchRebuilder,
)
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.projection_leases import MongoProjectionLeaseStore, ProjectionLeaseError
from event_platform.storage.rebuild_source import MongoRebuildSource
from event_platform.storage.rebuilds import MongoRebuildStore


def _at_or_after(current: str | None, boundary: str | None) -> bool:
    if boundary is None:
        return True
    if current is None:
        return False
    try:
        return tuple(map(int, current.split(":", 1))) >= tuple(map(int, boundary.split(":", 1)))
    except (TypeError, ValueError):
        return current >= boundary


@asynccontextmanager
async def configured_rebuild_runtime(
    settings: ServiceSettings,
) -> AsyncIterator[SearchRebuilder]:
    """Construct the same Mongo/ES/projector graph used by the service.

    The command owns a projector for the duration of the rebuild. Existing
    application processes can run the same graph independently; Mongo leases
    and checkpoint CAS keep ownership safe across those processes.
    """

    if settings.mongo_url is None or settings.elasticsearch_url is None:
        raise RebuildError("rebuild_unexpected_failure")
    timeout_ms = int(settings.dependency_timeout_seconds * 1000)
    mongo: AsyncMongoClient[Any] = AsyncMongoClient(
        settings.mongo_url,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
    )
    elasticsearch: AsyncElasticsearch = create_client(
        settings.elasticsearch_url,
        request_timeout=settings.dependency_timeout_seconds,
    )
    projector_task: asyncio.Task[object] | None = None
    lease = None
    lease_store: MongoProjectionLeaseStore | None = None
    projector: SearchProjector | None = None
    try:
        database = mongo[settings.mongo_database]
        events = database[settings.mongo_collection]
        await ensure_search_alias(elasticsearch, settings.elasticsearch_alias)
        source = MongoRebuildSource(events)
        state = MongoRebuildStore(database["search_rebuilds"], database["search_rebuild_leases"])
        checkpoint = MongoProjectionCheckpointStore(database["search_projection_checkpoints"])
        lease_store = MongoProjectionLeaseStore(database["search_projection_leases"])
        owner = f"rebuild-cli-{uuid4().hex}"
        projector = SearchProjector(
            projector="events-search",
            checkpoint=checkpoint,
            writer=ElasticsearchProjectionWriter(
                elasticsearch,
                alias=settings.elasticsearch_alias,
            ),
            owner=owner,
            generation=0,
        )
        lease = await lease_store.acquire(projector="events-search", owner=owner)
        if lease is None:
            raise ProjectionLeaseError("projector_lease_unavailable")
        projector.set_ownership(owner=lease.owner, generation=lease.generation)
        change_source = MongoChangeStreamSource(events)
        projector_task = asyncio.create_task(projector.run_source(change_source))

        async def capture_boundary() -> RebuildBoundary:
            upper = await source.capture_backfill_upper_bound()
            position = projector.change_stream_position()
            if upper is not None and position is None:
                deadline = (
                    asyncio.get_running_loop().time() + settings.dependency_timeout_seconds * 12
                )
                while position is None:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise RebuildError("projection_convergence_timeout", transient=True)
                    await asyncio.sleep(0.05)
                    position = projector.change_stream_position()
            return RebuildBoundary(upper, position)

        async def wait_for_convergence(boundary: RebuildBoundary) -> RebuildConvergence:
            token = projector.resume_token()
            latest = await change_source.latest_position(resume_after=token) if token else None
            target = latest or boundary.change_stream_position
            if target is None:
                return RebuildConvergence(backfill_upper_bound=boundary.backfill_upper_bound)
            deadline = asyncio.get_running_loop().time() + settings.dependency_timeout_seconds * 12
            while True:
                marker = projector.change_stream_position()
                if _at_or_after(marker, target):
                    return RebuildConvergence(
                        backfill_upper_bound=boundary.backfill_upper_bound,
                        projector_change_stream_position=marker,
                    )
                if asyncio.get_running_loop().time() >= deadline:
                    raise RebuildError("projection_convergence_timeout", transient=True)
                await asyncio.sleep(0.05)

        rebuilder = SearchRebuilder(
            state=state,
            search=ElasticsearchRebuildAdapter(elasticsearch),
            source=source,
            owner=owner,
            source_collection=settings.mongo_collection,
            alias=settings.elasticsearch_alias,
            set_live_target=projector.set_target_index,
            capture_boundary=capture_boundary,
            wait_for_convergence=wait_for_convergence,
        )
        yield rebuilder
    finally:
        if projector_task is not None:
            # The change stream may be blocked in socket I/O; cancellation is
            # bounded by the configured Mongo socket timeout.
            projector_task.cancel()
            await asyncio.gather(projector_task, return_exceptions=True)
        if projector is not None:
            projector.stop()
        if lease is not None and lease_store is not None:
            try:
                await lease_store.release(lease)
            except Exception:
                pass
        await elasticsearch.close()
        await mongo.close()
