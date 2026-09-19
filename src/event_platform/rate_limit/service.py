"""Route classification and backend selection for HTTP rate limiting."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from event_platform.observability.metrics import MetricsRegistry
from event_platform.rate_limit.identity import normalize_client_identity
from event_platform.rate_limit.local_bucket import LocalLeakyBucket
from event_platform.rate_limit.models import (
    MIN_REFILL_PER_SECOND,
    RateDecision,
    RouteClass,
    RoutePolicy,
)
from event_platform.rate_limit.redis_bucket import RateLimitUnavailable, RedisLeakyBucket

logger = logging.getLogger("event_platform.rate_limit")


class RateLimiter:
    def __init__(
        self,
        *,
        policies: Mapping[RouteClass, RoutePolicy],
        local_bucket: LocalLeakyBucket,
        redis_bucket: RedisLeakyBucket | None = None,
        trusted_proxy_hops: int = 0,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not 0 <= trusted_proxy_hops <= 10:
            raise ValueError("trusted proxy hops are outside bounds")
        required = {
            RouteClass.INGESTION,
            RouteClass.NORMAL_READ,
            RouteClass.EXPENSIVE_READ,
            RouteClass.OPS,
        }
        if not required.issubset(policies):
            raise ValueError("rate-limit policy registry is incomplete")
        if any(
            policy.route_class is not route_class or (route_class in required and policy.exempt)
            for route_class, policy in policies.items()
        ):
            raise ValueError("rate-limit policy route class does not match registry key")
        self.policies = MappingProxyType(dict(policies))
        self.local_bucket = local_bucket
        self.redis_bucket = redis_bucket
        self.trusted_proxy_hops = trusted_proxy_hops
        self.metrics = metrics

    async def check(
        self,
        scope: Mapping[str, object],
        *,
        method: str,
        path: str,
        request_id: str | None = None,
    ) -> RateDecision | None:
        route_class = classify_route(method=method, path=path)
        if route_class is None:
            return None
        policy = self.policies[route_class]
        if policy.exempt:
            return None
        identity = normalize_client_identity(scope, trusted_proxy_hops=self.trusted_proxy_hops)
        key = _bucket_key(identity, route_class)
        if self.redis_bucket is not None:
            try:
                decision = await self.redis_bucket.consume(key, policy)
                self._emit_decision(route_class, decision, request_id)
                return decision
            except RateLimitUnavailable as error:
                logger.info(
                    "rate limiter using local fallback",
                    extra={
                        "event": "rate_limit.degraded",
                        "operation": error.operation,
                        "route_class": route_class.value,
                        "request_id": request_id,
                    },
                )
                if self.metrics is not None:
                    self.metrics.inc(
                        "event_platform_rate_limit_decisions_total",
                        {"backend": "local", "outcome": "degraded"},
                    )
        else:
            logger.info(
                "rate limiter using local fallback",
                extra={
                    "event": "rate_limit.degraded",
                    "operation": "unconfigured",
                    "route_class": route_class.value,
                    "request_id": request_id,
                },
            )
        decision = await self.local_bucket.consume(key, _conservative(policy))
        self._emit_decision(route_class, decision, request_id)
        return decision

    def _emit_decision(
        self, route_class: RouteClass, decision: RateDecision, request_id: str | None
    ) -> None:
        outcome = "deny" if not decision.allowed else "queue" if decision.delay_seconds else "allow"
        logger.info(
            "rate limiter decision",
            extra={
                "event": f"rate_limit.{outcome}",
                "route_class": route_class.value,
                "backend": decision.backend,
                "request_id": request_id,
            },
        )
        if self.metrics is not None:
            metric_outcome = {"allow": "allowed", "queue": "queued", "deny": "denied"}[outcome]
            self.metrics.inc(
                "event_platform_rate_limit_decisions_total",
                {
                    "backend": decision.backend,
                    "outcome": metric_outcome,
                },
            )


def classify_route(*, method: str, path: str) -> RouteClass | None:
    normalized = path.rstrip("/") or "/"
    if normalized in {"/health/live", "/health/ready", "/health/components", "/metrics"}:
        return None
    if normalized == "/events" and method.upper() in {"POST", "PUT", "PATCH"}:
        return RouteClass.INGESTION
    if normalized.startswith(("/search", "/stats", "/events/stats")):
        return RouteClass.EXPENSIVE_READ
    if normalized.startswith(("/rebuild", "/admin", "/ops")):
        return RouteClass.OPS
    return RouteClass.NORMAL_READ


def _bucket_key(identity: str, route_class: RouteClass) -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{route_class.value}:{digest}"


def _conservative(policy: RoutePolicy) -> RoutePolicy:
    capacity = max(policy.cost, int(policy.capacity * 0.5))
    return replace(
        policy,
        capacity=capacity,
        refill_per_second=max(MIN_REFILL_PER_SECOND, policy.refill_per_second * 0.5),
    )
