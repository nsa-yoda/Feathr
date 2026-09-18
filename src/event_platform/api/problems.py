"""Safe RFC 9457-style problem responses for the HTTP boundary."""

import json
import logging
from collections.abc import Mapping
from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class ProblemResponse(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    error_code: str
    request_id: str


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
        instance=request.url.path,
        error_code=error_code,
        request_id=request_id,
    )
    response = JSONResponse(
        status_code=status,
        content=body.model_dump(),
        media_type="application/problem+json",
        headers=headers,
    )
    response.headers["X-Request-ID"] = request_id
    return response


async def handle_http_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
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
    assert isinstance(error, RequestValidationError)
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
        json.dumps(
            {
                "event": "http.unhandled_error",
                "request_id": request_id,
                "error_type": type(error).__name__,
                "status": 500,
            },
            separators=(",", ":"),
        )
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
