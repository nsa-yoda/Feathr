"""Assign safe request and operation correlation IDs to each HTTP request."""

import logging
import time
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from event_platform.observability.metrics import MetricsRegistry, normalize_route

logger = logging.getLogger("event_platform.http")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        request_id = _safe_request_id(scope) or str(uuid4())
        operation_id = str(uuid4())
        state["request_id"] = request_id
        state["operation_id"] = operation_id
        started_at = time.perf_counter()
        app = scope.get("app")
        metrics = getattr(getattr(app, "state", None), "metrics", None)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Operation-ID"] = operation_id
                status = int(message.get("status", 500))
                if isinstance(metrics, MetricsRegistry):
                    metrics.observe_http(
                        method=_method(scope),
                        path=str(scope.get("path", "/")),
                        status=status,
                        duration_seconds=max(0.0, time.perf_counter() - started_at),
                    )
                logger.info(
                    "HTTP request completed",
                    extra={
                        "event": "http.request_completed",
                        "request_id": request_id,
                        "operation_id": operation_id,
                        "method": _method(scope),
                        "path": normalize_route(str(scope.get("path", "/"))),
                        "status": status,
                    },
                )
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def _safe_request_id(scope: Scope) -> str | None:
    raw = next(
        (value for key, value in scope.get("headers", []) if key.lower() == b"x-request-id"),
        None,
    )
    if raw is None or len(raw) > 128:
        return None
    try:
        decoded = raw.decode("ascii")
        candidate = str(UUID(decoded))
        return candidate if decoded == candidate else None
    except (UnicodeDecodeError, ValueError):
        return None


def _method(scope: Scope) -> str:
    return str(scope.get("method", "GET")).upper()
