"""FastAPI application factory and lifespan ownership."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from event_platform.api.middleware.rate_limit import RateLimitMiddleware
from event_platform.api.middleware.request_id import RequestIdMiddleware
from event_platform.api.problems import register_problem_handlers
from event_platform.api.routes.events import router as events_router
from event_platform.api.routes.health import router as health_router
from event_platform.api.routes.query import router as query_router
from event_platform.api.routes.realtime_stats import router as realtime_stats_router
from event_platform.api.routes.rebuild import router as rebuild_router
from event_platform.api.routes.search import router as search_router
from event_platform.api.routes.stats import router as stats_router
from event_platform.cache.realtime import RedisCache
from event_platform.core.lifecycle import CloseCallback, LifecycleSupervisor, TaskFactory
from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings
from event_platform.observability.health import HealthRegistry
from event_platform.observability.metrics import MetricsRegistry
from event_platform.queue import InProcessQueue
from event_platform.rate_limit import LocalTokenBucket, RedisTokenBucket, RouteClass, RoutePolicy
from event_platform.rate_limit.service import RateLimiter
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.elasticsearch import create_client as create_elasticsearch_client
from event_platform.search.projection import SearchProjector
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.mongo import MongoEventStore
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
        redis_client: Redis | None = None
        mongo_client: AsyncMongoClient[Any] | None = None
        elasticsearch_client: AsyncElasticsearch | None = None
        supervisor: LifecycleSupervisor | None = None
        resources: list[tuple[str, CloseCallback]] = []
        search_projector: SearchProjector | None = None
        injected_event_store = getattr(app.state, "event_store", None)
        try:
            app.state.queue = InProcessQueue(
                capacity=app.state.settings.queue_capacity,
                visibility_timeout=app.state.settings.queue_visibility_timeout,
                send_timeout=app.state.settings.queue_send_timeout,
            )
            resources.append(("queue", app.state.queue.close))
            app.state.metrics = MetricsRegistry()
            app.state.health = HealthRegistry(app.state.metrics)
            app.state.mongo_ready = False
            app.state.persistence_worker_ready = False
            app.state.search_projector = None

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
                redis_client = Redis.from_url(app.state.settings.redis_url)
                resources.append(("redis", redis_client.aclose))
                app.state.realtime_cache = RedisCache(redis_client)
            else:
                app.state.realtime_cache = None
            if app.state.settings.mongo_url:
                mongo_client = AsyncMongoClient(app.state.settings.mongo_url)
                resources.append(("mongo", mongo_client.close))
                app.state.mongo_client = mongo_client
                mongo_database = mongo_client[app.state.settings.mongo_database]
                event_collection = mongo_database[app.state.settings.mongo_collection]
                app.state.event_store = MongoEventStore(event_collection)
            else:
                app.state.mongo_client = None
                app.state.event_store = injected_event_store
            if app.state.settings.elasticsearch_url:
                elasticsearch_client = create_elasticsearch_client(
                    app.state.settings.elasticsearch_url
                )
                resources.insert(
                    next(
                        (index for index, (name, _) in enumerate(resources) if name == "mongo"),
                        len(resources),
                    ),
                    ("elasticsearch", elasticsearch_client.close),
                )
                app.state.elasticsearch_client = elasticsearch_client
            else:
                app.state.elasticsearch_client = None
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
                local_bucket=LocalTokenBucket(
                    max_entries=settings_value.rate_limit_local_max_entries
                ),
                redis_bucket=RedisTokenBucket(redis_client) if redis_client is not None else None,
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
                search_projector = SearchProjector(
                    projector="events-search",
                    checkpoint=checkpoint,
                    writer=ElasticsearchProjectionWriter(
                        elasticsearch_client,
                        alias=app.state.settings.elasticsearch_alias,
                    ),
                )
                source = MongoChangeStreamSource(event_collection)
                app.state.search_projector = search_projector

                async def run_search_projector(stop_event: asyncio.Event) -> None:
                    projection_task = asyncio.create_task(search_projector.run_source(source))
                    stop_wait = asyncio.create_task(stop_event.wait())
                    try:
                        done, _ = await asyncio.wait(
                            (projection_task, stop_wait),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if stop_wait in done and not projection_task.done():
                            search_projector.stop()
                            projection_task.cancel()
                        await asyncio.gather(projection_task, return_exceptions=False)
                    finally:
                        if not stop_wait.done():
                            stop_wait.cancel()
                        await asyncio.gather(stop_wait, return_exceptions=True)

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
                )
                app.state.persistence_worker = worker

                async def run_persistence_worker(stop_event: asyncio.Event) -> None:
                    app.state.persistence_worker_ready = True
                    try:
                        await worker.run(stop_event)
                    finally:
                        app.state.persistence_worker_ready = False

                task_factories.setdefault("persistence_worker", run_persistence_worker)
            await supervisor.start(task_factories)
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
            del app.state.event_store
            del app.state.search_projector
            del app.state.metrics
            del app.state.health

    app = FastAPI(
        title="Distributed Event Processing Platform",
        debug=False,
        lifespan=lifespan,
    )
    app.add_middleware(RateLimitMiddleware)
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
