"""Consistent browser-facing security response headers."""

from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault(
                    "Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'"
                )
                settings = getattr(getattr(scope.get("app"), "state", None), "settings", None)
                if getattr(settings, "env", "local") == "production":
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class ConfiguredCORSMiddleware:
    """Apply exact-origin CORS from lifespan-loaded settings."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._cors: CORSMiddleware | None = None
        self._origin: str | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = getattr(getattr(scope.get("app"), "state", None), "settings", None)
        origin = getattr(settings, "cors_allowed_origin", None)
        if self._cors is None or self._origin != origin:
            self._origin = origin
            self._cors = CORSMiddleware(
                self.app,
                allow_origins=[origin] if origin else [],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Request-ID",
                    "Idempotency-Key",
                ],
                expose_headers=[
                    "X-Request-ID",
                    "X-Operation-ID",
                    "RateLimit-Limit",
                    "RateLimit-Remaining",
                    "RateLimit-Reset",
                    "X-Cache",
                ],
                allow_credentials=False,
            )
        assert self._cors is not None
        await self._cors(scope, receive, send)
