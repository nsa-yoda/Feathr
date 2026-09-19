"""FastAPI application factory and lifespan ownership."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings
from event_platform.queue import InProcessQueue
from event_platform.rate_limit import LocalTokenBucket, RedisTokenBucket, RouteClass, RoutePolicy
from event_platform.rate_limit.service import RateLimiter

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
        redis_client = None
        try:
            app.state.queue = InProcessQueue(
                capacity=app.state.settings.queue_capacity,
                visibility_timeout=app.state.settings.queue_visibility_timeout,
                send_timeout=app.state.settings.queue_send_timeout,
            )
            if app.state.settings.redis_url:
                from redis.asyncio import Redis

                redis_client = Redis.from_url(app.state.settings.redis_url)
                app.state.realtime_cache = RedisCache(redis_client)
            else:
                app.state.realtime_cache = None
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
            )
        except (TypeError, ValueError) as error:
            if redis_client is not None:
                await redis_client.aclose()
            await app.state.queue.close()
            logger.error(
                "service startup failed",
                extra={
                    "event": "service.startup_failed",
                    "error_type": type(error).__name__,
                    "error_fields": ["EVENT_PLATFORM_REDIS_URL"],
                },
            )
            raise SettingsStartupError(
                "Invalid Redis configuration.", fields=("EVENT_PLATFORM_REDIS_URL",)
            ) from None
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
            await app.state.queue.close()
            if redis_client is not None:
                await redis_client.aclose()
            logger.info("service shutdown complete", extra={"event": "service.shutdown"})
            del app.state.settings
            del app.state.queue
            del app.state.rate_limiter

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
