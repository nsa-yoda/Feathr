"""ASGI middleware for route-class rate limiting."""

from __future__ import annotations

from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from event_platform.api.problems import ProblemResponse, _safe_instance
from event_platform.rate_limit.models import RateDecision
from event_platform.rate_limit.service import RateLimiter, classify_route


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        if classify_route(method=request.method, path=request.url.path) is None:
            await self.app(scope, receive, send)
            return
        app = scope.get("app")
        limiter = getattr(getattr(app, "state", None), "rate_limiter", None)
        request_id = str(scope.get("state", {}).get("request_id") or uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        if not isinstance(limiter, RateLimiter):
            body = ProblemResponse(
                title="Service Unavailable",
                status=503,
                detail="The service is not ready to accept requests.",
                instance=_safe_instance(request.url.path),
                error_code="service_not_ready",
                request_id=UUID(request_id),
            )
            await JSONResponse(
                status_code=503,
                content=body.model_dump(mode="json"),
                media_type="application/problem+json",
                headers={"Retry-After": "1", "X-Request-ID": request_id},
            )(scope, receive, send)
            return
        decision = await limiter.check(
            scope,
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        if decision is not None and not decision.allowed:
            body = ProblemResponse(
                title="Too Many Requests",
                status=429,
                detail="The request rate limit was exceeded.",
                instance=_safe_instance(request.url.path),
                error_code="rate_limit_exceeded",
                request_id=UUID(request_id),
            )
            headers = _rate_headers(decision, denied=True)
            headers["X-Request-ID"] = request_id
            await JSONResponse(
                status_code=429,
                content=body.model_dump(mode="json"),
                media_type="application/problem+json",
                headers=headers,
            )(scope, receive, send)
            return

        async def send_with_rate_headers(message: Message) -> None:
            if message["type"] == "http.response.start" and decision is not None:
                _apply_headers(MutableHeaders(scope=message), decision, denied=False)
            await send(message)

        await self.app(scope, receive, send_with_rate_headers)


def _rate_headers(decision: RateDecision, denied: bool) -> dict[str, str]:
    limit = decision.limit
    remaining = decision.remaining
    reset_at = decision.reset_at
    headers = {
        "RateLimit-Limit": str(limit),
        "RateLimit-Remaining": str(max(0, remaining)),
        "RateLimit-Reset": str(max(0, reset_at)),
    }
    if denied:
        headers["Retry-After"] = str(max(1, decision.retry_after))
    return headers


def _apply_headers(target: MutableHeaders, decision: RateDecision, denied: bool) -> None:
    for name, value in _rate_headers(decision, denied=denied).items():
        target[name] = value
