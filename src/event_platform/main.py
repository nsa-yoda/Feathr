"""FastAPI application factory and lifespan ownership."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from event_platform.api.middleware.body_limit import BodyLimitMiddleware
from event_platform.api.middleware.production_auth import ProductionAuthMiddleware
from event_platform.api.middleware.rate_limit import RateLimitMiddleware
from event_platform.api.middleware.request_id import RequestIdMiddleware
from event_platform.api.middleware.security_headers import (
    ConfiguredCORSMiddleware,
    SecurityHeadersMiddleware,
)
from event_platform.api.problems import register_problem_handlers
from event_platform.api.routes.events import router as events_router
from event_platform.api.routes.health import router as health_router
from event_platform.api.routes.query import router as query_router
from event_platform.api.routes.realtime_stats import router as realtime_stats_router
from event_platform.api.routes.rebuild import router as rebuild_router
from event_platform.api.routes.search import router as search_router
from event_platform.api.routes.stats import router as stats_router
from event_platform.cache.realtime import RedisCache
from event_platform.core.composition import build_application_services
from event_platform.core.lifecycle import (
    CloseCallback,
    LifecycleSupervisor,
    TaskFactory,
    TaskPolicy,
)
from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings
from event_platform.observability.health import HealthRegistry
from event_platform.observability.metrics import MetricsRegistry
from event_platform.queue import InProcessQueue
from event_platform.rate_limit import LocalLeakyBucket, RedisLeakyBucket, RouteClass, RoutePolicy
from event_platform.rate_limit.service import RateLimiter
from event_platform.search.bootstrap import ensure_search_alias
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.elasticsearch import create_client as create_elasticsearch_client
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.projection import SearchProjector
from event_platform.search.rebuild import RebuildConvergence, SearchRebuilder
from event_platform.search.search import ElasticsearchSearchService, SearchClient
from event_platform.storage.bootstrap import (
    SCHEMA_VERSION,
    StorageCollections,
    StorageDatabase,
    StorageSchemaError,
    verify_storage,
)
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.idempotency import InMemoryIdempotencyRegistry, MongoIdempotencyRegistry
from event_platform.storage.mongo import MongoEventStore
from event_platform.storage.projection_leases import MongoProjectionLeaseStore, ProjectionLeaseError
from event_platform.storage.rebuild_source import MongoRebuildSource
from event_platform.storage.rebuilds import MongoRebuildStore
from event_platform.worker.persistence import PersistenceWorker

logger = logging.getLogger("event_platform.lifecycle")


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    """Create the ASGI app without opening dependency clients at import time."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.settings = settings if settings is not None else load_settings()
        except SettingsStartupError as error:
            configure_logging("INFO")
            logger.error(
                "service startup failed",
                extra={
                    "event": "service.startup_failed",
                    "error_type": type(error).__name__,
                    "error_fields": list(error.fields),
                },
            )
            raise

        configure_logging(app.state.settings.log_level)
        app.state.cursor_signing_key = (
            app.state.settings.cursor_signing_key.encode()
            if app.state.settings.cursor_signing_key
            else None
        )
        previous_cursor_key = (
            app.state.settings.cursor_previous_signing_key.encode()
            if app.state.settings.cursor_previous_signing_key
            else None
        )
        app.state.cursor_keys = tuple(
            key for key in (app.state.cursor_signing_key, previous_cursor_key) if key is not None
        )
        redis_client: Redis | None = None
        mongo_client: AsyncMongoClient[Any] | None = None
        elasticsearch_client: AsyncElasticsearch | None = None
        supervisor: LifecycleSupervisor | None = None
        resources: list[tuple[str, CloseCallback]] = []
        search_projector: SearchProjector | None = None
        injected_event_store = getattr(app.state, "event_store", None)
        injected_search_service = getattr(app.state, "search_service", None)
        try:
            app.state.metrics = MetricsRegistry()
            app.state.queue = InProcessQueue(
                capacity=app.state.settings.queue_capacity,
                visibility_timeout=app.state.settings.queue_visibility_timeout,
                send_timeout=app.state.settings.queue_send_timeout,
                metrics=app.state.metrics,
            )
            resources.append(("queue", app.state.queue.close))
            app.state.health = HealthRegistry(app.state.metrics)
            app.state.services = build_application_services(
                queue=app.state.queue,
                metrics=app.state.metrics,
                health=app.state.health,
            )
            app.state.mongo_ready = False
            app.state.persistence_worker_ready = False
            app.state.search_projector = None
            app.state.rebuilder = None

            async def mongo_probe() -> bool:
                if mongo_client is None:
                    return False
                try:
                    await asyncio.wait_for(mongo_client.admin.command("ping"), timeout=0.5)
                except Exception as error:
                    logger.warning(
                        "mongo health probe degraded",
                        extra={
                            "event": "health.mongo_degraded",
                            "component": "mongo",
                            "error_type": type(error).__name__,
                            "state": "unhealthy",
                        },
                    )
                    return False
                app.state.mongo_ready = True
                return True

            async def redis_probe() -> str | bool:
                if redis_client is None:
                    return "degraded"
                try:
                    await asyncio.wait_for(redis_client.ping(), timeout=0.25)
                except Exception as error:
                    logger.warning(
                        "redis health probe degraded",
                        extra={
                            "event": "health.redis_degraded",
                            "component": "redis",
                            "error_type": type(error).__name__,
                            "state": "degraded",
                        },
                    )
                    return "degraded"
                return True

            app.state.health.set_probe("mongo", mongo_probe)
            app.state.health.set_probe("redis", redis_probe)

            async def elasticsearch_probe() -> str | bool:
                if elasticsearch_client is None:
                    return "degraded"
                try:
                    await asyncio.wait_for(elasticsearch_client.info(), timeout=0.5)
                except Exception as error:
                    logger.warning(
                        "elasticsearch health probe degraded",
                        extra={
                            "event": "health.elasticsearch_degraded",
                            "component": "elasticsearch",
                            "error_type": type(error).__name__,
                            "state": "degraded",
                        },
                    )
                    return "degraded"
                return True

            app.state.health.set_probe("elasticsearch", elasticsearch_probe)
            app.state.health.set_probe(
                "search_projector",
                lambda: (
                    "degraded"
                    if supervisor is None or not supervisor.has_task("search_projector")
                    else supervisor.task_healthy("search_projector")
                ),
            )
            app.state.health.set_probe("queue", lambda: not app.state.queue.closed)
            app.state.health.set_probe(
                "persistence_worker",
                lambda: bool(
                    supervisor is not None
                    and supervisor.all_tasks_healthy()
                    and (
                        getattr(app.state, "persistence_worker_ready", False)
                        or supervisor.task_healthy("persistence_worker")
                    )
                ),
            )
            if app.state.settings.redis_url:
                timeout = app.state.settings.dependency_timeout_seconds
                redis_client = Redis.from_url(
                    app.state.settings.redis_url,
                    socket_connect_timeout=timeout,
                    socket_timeout=timeout,
                )
                resources.append(("redis", redis_client.aclose))
                app.state.realtime_cache = RedisCache(redis_client, metrics=app.state.metrics)
            else:
                app.state.realtime_cache = None
            if app.state.settings.mongo_url:
                timeout_ms = int(app.state.settings.dependency_timeout_seconds * 1000)
                mongo_client = AsyncMongoClient(
                    app.state.settings.mongo_url,
                    serverSelectionTimeoutMS=timeout_ms,
                    connectTimeoutMS=timeout_ms,
                    socketTimeoutMS=timeout_ms,
                )
                resources.append(("mongo", mongo_client.close))
                app.state.mongo_client = mongo_client
                mongo_database = mongo_client[app.state.settings.mongo_database]
                event_collection = mongo_database[app.state.settings.mongo_collection]
                try:
                    verification = await verify_storage(
                        cast(StorageDatabase, mongo_database),
                        collections=StorageCollections(events=app.state.settings.mongo_collection),
                    )
                except StorageSchemaError as error:
                    logger.error(
                        "storage verification failed",
                        extra={
                            "event": "storage.verification_failed",
                            "component": "mongo",
                            "classification": error.classification,
                            "collection": error.collection,
                            "index": error.index,
                            "schema_version": SCHEMA_VERSION,
                        },
                    )
                    raise
                logger.info(
                    "storage verification complete",
                    extra={
                        "event": "storage.verification_complete",
                        "component": "mongo",
                        "schema_version": verification.schema_version,
                        "manifest_fingerprint": verification.manifest_fingerprint,
                        "verified_indexes": verification.verified_indexes,
                    },
                )
                app.state.event_store = MongoEventStore(event_collection, metrics=app.state.metrics)
                app.state.services.event_store = app.state.event_store
                app.state.idempotency_registry = MongoIdempotencyRegistry(
                    mongo_database["event_idempotency"]
                )
                app.state.rebuild_store = MongoRebuildStore(
                    mongo_database["search_rebuilds"],
                    mongo_database["search_rebuild_leases"],
                )
                app.state.services.rebuild_store = app.state.rebuild_store
            else:
                app.state.mongo_client = None
                app.state.event_store = injected_event_store
                app.state.services.event_store = injected_event_store
                app.state.idempotency_registry = InMemoryIdempotencyRegistry()
                app.state.rebuild_store = getattr(app.state, "rebuild_store", None)
            if app.state.settings.elasticsearch_url:
                elasticsearch_client = create_elasticsearch_client(
                    app.state.settings.elasticsearch_url,
                    request_timeout=app.state.settings.dependency_timeout_seconds,
                )
                resources.insert(
                    next(
                        (index for index, (name, _) in enumerate(resources) if name == "mongo"),
                        len(resources),
                    ),
                    ("elasticsearch", elasticsearch_client.close),
                )
                app.state.elasticsearch_client = elasticsearch_client
                app.state.search_service = ElasticsearchSearchService(
                    cast(SearchClient, elasticsearch_client),
                    alias=app.state.settings.elasticsearch_alias,
                    cursor_key=(app.state.cursor_keys[0] if app.state.cursor_keys else None),
                    previous_cursor_key=(
                        app.state.cursor_keys[1] if len(app.state.cursor_keys) > 1 else None
                    ),
                    metrics=app.state.metrics,
                )
                app.state.services.search_service = app.state.search_service
                try:
                    await ensure_search_alias(
                        elasticsearch_client, app.state.settings.elasticsearch_alias
                    )
                except Exception as error:
                    logger.warning(
                        "search alias bootstrap degraded",
                        extra={
                            "event": "search.bootstrap_failed",
                            "component": "elasticsearch",
                            "error_type": type(error).__name__,
                            "classification": "derived_state_bootstrap",
                            "state": "degraded",
                        },
                    )
            else:
                app.state.elasticsearch_client = None
                app.state.search_service = injected_search_service
                app.state.services.search_service = injected_search_service
            settings_value = app.state.settings
            policies = {
                RouteClass.INGESTION: RoutePolicy(
                    RouteClass.INGESTION,
                    settings_value.rate_limit_ingestion_capacity,
                    settings_value.rate_limit_ingestion_refill,
                    settings_value.rate_limit_ingestion_cost,
                ),
                RouteClass.NORMAL_READ: RoutePolicy(
                    RouteClass.NORMAL_READ,
                    settings_value.rate_limit_normal_capacity,
                    settings_value.rate_limit_normal_refill,
                    settings_value.rate_limit_normal_cost,
                ),
                RouteClass.EXPENSIVE_READ: RoutePolicy(
                    RouteClass.EXPENSIVE_READ,
                    settings_value.rate_limit_expensive_capacity,
                    settings_value.rate_limit_expensive_refill,
                    settings_value.rate_limit_expensive_cost,
                ),
                RouteClass.OPS: RoutePolicy(
                    RouteClass.OPS,
                    settings_value.rate_limit_ops_capacity,
                    settings_value.rate_limit_ops_refill,
                    settings_value.rate_limit_ops_cost,
                ),
            }
            app.state.rate_limiter = RateLimiter(
                policies=policies,
                local_bucket=LocalLeakyBucket(
                    max_entries=settings_value.rate_limit_local_max_entries
                ),
                redis_bucket=RedisLeakyBucket(redis_client) if redis_client is not None else None,
                trusted_proxy_hops=settings_value.rate_limit_trusted_proxy_hops,
                metrics=app.state.metrics,
            )

            task_factories: dict[str, TaskFactory] = dict(
                getattr(app.state, "lifecycle_task_factories", {})
            )
            if mongo_client is not None and elasticsearch_client is not None:
                checkpoint = MongoProjectionCheckpointStore(
                    mongo_client[app.state.settings.mongo_database]["search_projection_checkpoints"]
                )
                lease_store = MongoProjectionLeaseStore(
                    mongo_client[app.state.settings.mongo_database]["search_projection_leases"]
                )
                projector_owner = f"api-{uuid4().hex}"
                search_projector = SearchProjector(
                    projector="events-search",
                    checkpoint=checkpoint,
                    writer=ElasticsearchProjectionWriter(
                        elasticsearch_client,
                        alias=app.state.settings.elasticsearch_alias,
                        metrics=app.state.metrics,
                    ),
                    owner=projector_owner,
                    generation=0,
                    metrics=app.state.metrics,
                )
                source = MongoChangeStreamSource(event_collection)
                rebuild_source = MongoRebuildSource(event_collection)
                app.state.search_projector = search_projector

                async def wait_for_rebuild_convergence(
                    initial: str | None,
                ) -> RebuildConvergence:
                    boundary = await rebuild_source.capture_high_water()
                    if boundary is None:
                        return RebuildConvergence(
                            source_high_water=initial,
                            projector_checkpoint=initial,
                        )
                    marker = search_projector.checkpoint_marker()
                    if marker is None and boundary == initial:
                        return RebuildConvergence(
                            source_high_water=boundary,
                            projector_checkpoint=boundary,
                        )
                    deadline = (
                        asyncio.get_running_loop().time()
                        + app.state.settings.dependency_timeout_seconds * 12
                    )
                    while True:
                        marker = search_projector.checkpoint_marker()
                        if marker is not None and marker >= boundary:
                            return RebuildConvergence(
                                source_high_water=boundary,
                                projector_checkpoint=marker,
                            )
                        if asyncio.get_running_loop().time() >= deadline:
                            raise RuntimeError("projection convergence timed out")
                        await asyncio.sleep(0.05)

                app.state.rebuilder = SearchRebuilder(
                    state=app.state.rebuild_store,
                    search=ElasticsearchRebuildAdapter(elasticsearch_client),
                    source=rebuild_source,
                    owner=f"api-rebuild-{uuid4().hex}",
                    source_collection=app.state.settings.mongo_collection,
                    alias=app.state.settings.elasticsearch_alias,
                    set_live_target=search_projector.set_target_index,
                    wait_for_convergence=wait_for_rebuild_convergence,
                )

                async def run_search_projector(stop_event: asyncio.Event) -> None:
                    lease = await lease_store.acquire(
                        projector="events-search", owner=projector_owner
                    )
                    if lease is None:
                        raise ProjectionLeaseError("projector_lease_unavailable")
                    search_projector.set_ownership(owner=lease.owner, generation=lease.generation)
                    projection_task = asyncio.create_task(search_projector.run_source(source))
                    stop_wait = asyncio.create_task(stop_event.wait())
                    lease_lost = asyncio.Event()

                    async def renew_lease() -> None:
                        nonlocal lease
                        assert lease is not None
                        while not stop_event.is_set():
                            await asyncio.sleep(10.0)
                            renewed = await lease_store.renew(lease)
                            if renewed is None:
                                lease_lost.set()
                                search_projector.stop()
                                return
                            lease = renewed

                    renewal_task = asyncio.create_task(renew_lease())
                    lease_lost_wait = asyncio.create_task(lease_lost.wait())
                    try:
                        done, _ = await asyncio.wait(
                            (projection_task, stop_wait, lease_lost_wait),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if lease_lost.is_set() and not projection_task.done():
                            projection_task.cancel()
                            raise ProjectionLeaseError("projector_lease_lost")
                        if stop_wait in done and not projection_task.done():
                            search_projector.stop()
                            projection_task.cancel()
                        await asyncio.gather(projection_task, return_exceptions=False)
                    finally:
                        if not stop_wait.done():
                            stop_wait.cancel()
                        if not renewal_task.done():
                            renewal_task.cancel()
                        if not lease_lost_wait.done():
                            lease_lost_wait.cancel()
                        await lease_store.release(lease)
                        await asyncio.gather(stop_wait, return_exceptions=True)
                        await asyncio.gather(renewal_task, return_exceptions=True)
                        await asyncio.gather(lease_lost_wait, return_exceptions=True)

                task_factories.setdefault("search_projector", run_search_projector)
            supervisor = LifecycleSupervisor(
                app.state.queue,
                grace_period=app.state.settings.shutdown_grace_period,
                resources=resources,
                logger=logger,
            )
            app.state.lifecycle = supervisor
            if mongo_client is not None and app.state.event_store is not None:
                worker = PersistenceWorker(
                    app.state.queue,
                    app.state.event_store,
                    concurrency=app.state.settings.worker_concurrency,
                    metrics=app.state.metrics,
                )
                app.state.persistence_worker = worker

                async def run_persistence_worker(stop_event: asyncio.Event) -> None:
                    app.state.persistence_worker_ready = True
                    try:
                        await worker.run(stop_event)
                    finally:
                        app.state.persistence_worker_ready = False

                task_factories.setdefault("persistence_worker", run_persistence_worker)
            await supervisor.start(
                task_factories,
                policies={
                    name: (
                        TaskPolicy("degradable")
                        if name == "search_projector"
                        else TaskPolicy(drain_on_shutdown=name == "persistence_worker")
                    )
                    for name in task_factories
                },
            )
            app.state.metrics.inc("event_platform_lifecycle_events_total", {"outcome": "startup"})
        except Exception as error:
            if supervisor is not None:
                await supervisor.shutdown()
            elif resources:
                startup_cleanup = LifecycleSupervisor(
                    app.state.queue,
                    grace_period=app.state.settings.shutdown_grace_period,
                    resources=resources,
                    logger=logger,
                )
                await startup_cleanup.shutdown()
            logger.error(
                "service startup failed",
                extra={
                    "event": "service.startup_failed",
                    "error_type": type(error).__name__,
                    "error_fields": ["startup"],
                },
            )
            raise SettingsStartupError("Service startup failed.", fields=("startup",)) from None
        logger.info(
            "service startup complete",
            extra={
                "event": "service.startup",
                "environment": app.state.settings.env,
            },
        )
        try:
            yield
        finally:
            if supervisor is not None:
                await supervisor.shutdown()
            logger.info("service shutdown complete", extra={"event": "service.shutdown"})
            if hasattr(app.state, "metrics"):
                app.state.metrics.inc(
                    "event_platform_lifecycle_events_total", {"outcome": "shutdown"}
                )
            del app.state.settings
            del app.state.queue
            del app.state.rate_limiter
            del app.state.lifecycle
            del app.state.mongo_client
            del app.state.elasticsearch_client
            del app.state.search_service
            del app.state.realtime_cache
            if hasattr(app.state, "realtime_stats_service"):
                del app.state.realtime_stats_service
            del app.state.event_store
            del app.state.search_projector
            del app.state.rebuilder
            del app.state.metrics
            del app.state.health

    app = FastAPI(
        title="Distributed Event Processing Platform",
        debug=False,
        lifespan=lifespan,
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(ConfiguredCORSMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ProductionAuthMiddleware)
    app.add_middleware(RequestIdMiddleware)
    register_problem_handlers(app)
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(query_router)
    app.include_router(search_router)
    app.include_router(rebuild_router)
    app.include_router(stats_router)
    app.include_router(realtime_stats_router)
    return app
