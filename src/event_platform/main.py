"""FastAPI application factory and lifespan ownership."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from event_platform.api.middleware.request_id import RequestIdMiddleware
from event_platform.api.problems import register_problem_handlers
from event_platform.api.routes.events import router as events_router
from event_platform.api.routes.health import router as health_router
from event_platform.api.routes.query import router as query_router
from event_platform.api.routes.search import router as search_router
from event_platform.api.routes.stats import router as stats_router
from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings
from event_platform.queue import InProcessQueue

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
        app.state.queue = InProcessQueue(
            capacity=app.state.settings.queue_capacity,
            visibility_timeout=app.state.settings.queue_visibility_timeout,
            send_timeout=app.state.settings.queue_send_timeout,
        )
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
            logger.info("service shutdown complete", extra={"event": "service.shutdown"})
            del app.state.settings
            del app.state.queue

    app = FastAPI(
        title="Distributed Event Processing Platform",
        debug=False,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    register_problem_handlers(app)
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(query_router)
    app.include_router(search_router)
    app.include_router(stats_router)
    return app
