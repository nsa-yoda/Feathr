"""FastAPI application factory and lifespan ownership."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from event_platform.api.middleware.request_id import RequestIdMiddleware
from event_platform.api.problems import register_problem_handlers
from event_platform.api.routes.health import router as health_router
from event_platform.core.logging import configure_logging
from event_platform.core.settings import ServiceSettings, SettingsStartupError, load_settings

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
                },
            )
            raise

        configure_logging(app.state.settings.log_level)
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
            logger.info("service shutdown complete", extra={"event": "service.shutdown"})
            del app.state.settings

    app = FastAPI(
        title="Distributed Event Processing Platform",
        debug=False,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    register_problem_handlers(app)
    app.include_router(health_router)
    return app
