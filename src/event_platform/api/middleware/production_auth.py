"""Fail-closed production authentication boundary for operator/API traffic."""

from __future__ import annotations

import hmac
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class ProductionAuthMiddleware:
    """Require a configured bearer token in production, except cheap liveness."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/health/live":
            await self.app(scope, receive, send)
            return
        settings = getattr(getattr(scope.get("app"), "state", None), "settings", None)
        if getattr(settings, "env", "local") != "production":
            await self.app(scope, receive, send)
            return
        expected = getattr(settings, "production_api_token", None)
        supplied = _authorization(scope)
        if (
            not isinstance(expected, str)
            or not supplied
            or not hmac.compare_digest(supplied, expected)
        ):
            request_id = str(scope.get("state", {}).get("request_id") or uuid4())
            response = JSONResponse(
                {
                    "type": "about:blank",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "authentication is required",
                    "instance": "/protected",
                    "error_code": "authentication_required",
                    "request_id": request_id,
                },
                status_code=401,
                media_type="application/problem+json",
                headers={"WWW-Authenticate": "Bearer", "X-Request-ID": request_id},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _authorization(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"authorization" and value.startswith(b"Bearer "):
            try:
                token = value[7:].decode("ascii")
            except UnicodeDecodeError:
                return None
            return token if 32 <= len(token) <= 256 else None
    return None
