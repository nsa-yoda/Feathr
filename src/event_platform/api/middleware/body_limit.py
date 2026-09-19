"""Reject oversized HTTP bodies before application parsers buffer them."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from event_platform.api.problems import ProblemResponse, _safe_instance


class RequestBodyTooLarge(Exception):
    """Internal control flow for a request body over the configured limit."""


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = 1_048_576) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        app = scope.get("app")
        configured_limit = getattr(getattr(app, "state", None), "settings", None)
        max_bytes = getattr(configured_limit, "request_body_max_bytes", self.max_bytes)
        max_query_bytes = getattr(configured_limit, "request_query_max_bytes", 8_192)
        if len(scope.get("query_string", b"")) > max_query_bytes:
            await _send_problem(
                scope,
                send,
                status=414,
                title="URI Too Long",
                detail="The request query exceeds the configured size limit.",
                error_code="request_query_too_large",
            )
            return
        content_length = _content_length(scope)
        if content_length is not None and content_length > max_bytes:
            await _send_problem(
                scope,
                send,
                status=413,
                title="Payload Too Large",
                detail="The request body exceeds the configured size limit.",
                error_code="request_body_too_large",
            )
            return

        total = 0

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    total += len(body)
                    if total > max_bytes:
                        raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await _send_problem(
                scope,
                send,
                status=413,
                title="Payload Too Large",
                detail="The request body exceeds the configured size limit.",
                error_code="request_body_too_large",
            )


def _content_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() != b"content-length":
            continue
        try:
            parsed = int(value.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return None
        return parsed if parsed >= 0 else 0
    return None


async def _send_problem(
    scope: Scope,
    send: Send,
    *,
    status: int,
    title: str,
    detail: str,
    error_code: str,
) -> None:
    state = scope.setdefault("state", {})
    raw_request_id = state.get("request_id")
    try:
        request_id = UUID(str(raw_request_id)) if raw_request_id else uuid4()
    except ValueError:
        request_id = uuid4()
    body = ProblemResponse(
        title=title,
        status=status,
        detail=detail,
        instance=_safe_instance(str(scope.get("path", "/"))),
        error_code=error_code,
        request_id=request_id,
    ).model_dump(mode="json")
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    message: Message = {
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/problem+json"),
            (b"content-length", str(len(payload)).encode("ascii")),
            (b"x-request-id", str(request_id).encode("ascii")),
        ],
    }
    headers = MutableHeaders(scope=message)
    headers["Retry-After"] = "1"
    await send(message)
    await send({"type": "http.response.body", "body": payload})
