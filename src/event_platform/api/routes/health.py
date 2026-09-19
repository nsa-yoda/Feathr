"""Cheap liveness and dependency health routes."""

from typing import Any, Literal

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from event_platform.api.problems import ProblemResponse
from event_platform.observability.health import HealthRegistry, HealthSnapshot


def _problem_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": ProblemResponse.model_json_schema()}},
    }


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: _problem_response("Resource not found"),
    405: _problem_response("Method not allowed"),
    422: _problem_response("Request validation failed"),
    500: _problem_response("Unexpected application error"),
}

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"


@router.get(
    "/health/live",
    responses=PROBLEM_RESPONSES,
)
async def get_liveness() -> LiveResponse:
    return LiveResponse()


def _registry(request: Request) -> HealthRegistry:
    registry = getattr(request.app.state, "health", None)
    if not isinstance(registry, HealthRegistry):
        raise RuntimeError("health registry is not initialized")
    return registry


@router.get("/health/ready", response_model=HealthSnapshot, responses=PROBLEM_RESPONSES)
async def get_readiness(request: Request, response: Response) -> HealthSnapshot:
    ready, snapshot = await _registry(request).ready()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return snapshot


@router.get("/health/components", response_model=HealthSnapshot, responses=PROBLEM_RESPONSES)
async def get_components(request: Request) -> HealthSnapshot:
    return await _registry(request).snapshot()


@router.get("/metrics", include_in_schema=True, response_class=PlainTextResponse)
async def get_metrics(request: Request) -> PlainTextResponse:
    from event_platform.observability.metrics import MetricsRegistry

    metrics = getattr(request.app.state, "metrics", None)
    if not isinstance(metrics, MetricsRegistry):
        raise RuntimeError("metrics registry is not initialized")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
