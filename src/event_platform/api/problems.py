"""Safe RFC 9457-style problem responses for the HTTP boundary."""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from event_platform.observability.metrics import normalize_route

logger = logging.getLogger(__name__)
_MAX_PROBLEM_TEXT_LENGTH = 2048


class ProblemResponse(BaseModel):
    type: Annotated[str, Field(min_length=1, max_length=2048)] = "about:blank"
    title: Annotated[str, Field(min_length=1, max_length=2048)]
    status: Annotated[int, Field(ge=100, le=599)]
    detail: Annotated[str, Field(min_length=1, max_length=2048)]
    instance: Annotated[str, Field(min_length=1, max_length=2048)]
    error_code: Annotated[str, Field(min_length=1, max_length=256)]
    request_id: UUID


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        request_id = str(uuid4())
        request.state.request_id = request_id
    return str(request_id)


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    error_code: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body = ProblemResponse(
        title=title,
        status=status,
        detail=detail,
        instance=_safe_instance(request.url.path),
        error_code=error_code,
        request_id=request_id,
    )
    response = JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json"),
        media_type="application/problem+json",
        headers=headers,
    )
    response.headers["X-Request-ID"] = request_id
    operation_id = getattr(request.state, "operation_id", None)
    if operation_id is not None:
        response.headers["X-Operation-ID"] = str(operation_id)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    return response


def _safe_instance(path: str) -> str:
    """Keep problem instances bounded without echoing arbitrary path segments."""

    normalized = normalize_route(path)
    if normalized != "other":
        return normalized
    first_segment = next((segment for segment in path.split("/") if segment), "")
    return f"/{first_segment}"[:_MAX_PROBLEM_TEXT_LENGTH] or "/"


async def handle_http_error(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, StarletteHTTPException):
        return await handle_unexpected_error(request, error)
    status = error.status_code
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "HTTP Error"
    code = "route_not_found" if status == 404 else f"http_{status}"
    detail = (
        "The requested resource was not found."
        if status == 404
        else "The request could not be completed."
    )
    return _problem(
        request,
        status=status,
        title=title,
        detail=detail,
        error_code=code,
        headers=error.headers,
    )


async def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RequestValidationError):
        return await handle_unexpected_error(request, error)
    return _problem(
        request,
        status=422,
        title="Unprocessable Content",
        detail="The request did not meet the required input contract.",
        error_code="request_validation_failed",
    )


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error(
        "unhandled HTTP exception",
        extra={
            "event": "http.unhandled_error",
            "request_id": request_id,
            "error_type": type(error).__name__,
            "method": request.method,
            "path": normalize_route(request.url.path),
            "status": 500,
        },
    )
    return _problem(
        request,
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        error_code="internal_error",
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
