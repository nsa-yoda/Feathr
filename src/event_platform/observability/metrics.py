"""Small, dependency-free Prometheus registry with bounded labels."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Mapping
from re import match
from typing import Literal

_ROUTE_PATTERNS = (
    ("health_live", "/health/live"),
    ("health_ready", "/health/ready"),
    ("health_components", "/health/components"),
    ("metrics", "/metrics"),
    ("search", "/events/search"),
    ("realtime_stats", "/events/stats/realtime"),
    ("stats", "/events/stats"),
    ("rebuild", "/operations/search-rebuild"),
    ("events", "/events"),
)
_LABEL_RE = r"^[a-z][a-z0-9_]{0,31}$"
_METRIC_RE = r"^[a-z][a-z0-9_]{0,127}$"
_ALLOWED_LABELS = frozenset({"method", "route", "status", "component", "backend", "outcome"})
_ALLOWED_VALUES = {
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "OTHER"}),
    "route": frozenset(
        {
            "health_live",
            "health_ready",
            "health_components",
            "metrics",
            "events",
            "events_detail",
            "search",
            "stats",
            "realtime_stats",
            "rebuild",
            "other",
        }
    ),
    "status": frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "unknown"}),
    "component": frozenset(
        {
            "mongo",
            "elasticsearch",
            "redis",
            "queue",
            "persistence_worker",
            "search_projector",
        }
    ),
    "backend": frozenset({"local", "redis", "mongo", "elasticsearch", "queue"}),
    "outcome": frozenset(
        {
            "startup",
            "shutdown",
            "accepted",
            "allowed",
            "denied",
            "degraded",
            "hit",
            "miss",
            "bypass",
            "success",
            "failure",
        }
    ),
}
MetricName = Literal[
    "event_platform_http_requests_total",
    "event_platform_queue_operations_total",
    "event_platform_worker_operations_total",
    "event_platform_mongo_operations_total",
    "event_platform_elasticsearch_operations_total",
    "event_platform_redis_operations_total",
    "event_platform_rate_limit_decisions_total",
    "event_platform_lifecycle_events_total",
]
_METRIC_FAMILIES = frozenset(
    {
        "event_platform_http_requests_total",
        "event_platform_queue_operations_total",
        "event_platform_worker_operations_total",
        "event_platform_mongo_operations_total",
        "event_platform_elasticsearch_operations_total",
        "event_platform_redis_operations_total",
        "event_platform_rate_limit_decisions_total",
        "event_platform_lifecycle_events_total",
    }
)


def normalize_route(path: str) -> str:
    """Map arbitrary paths to a fixed route label without retaining identifiers."""

    for route, prefix in _ROUTE_PATTERNS:
        if path == prefix or (prefix != "/events" and path.startswith(prefix + "/")):
            return route
    if path.startswith("/events/"):
        return "events_detail"
    return "other"


def status_family(status: int) -> str:
    return f"{status // 100}xx" if 100 <= status <= 599 else "unknown"


class MetricsRegistry:
    """Thread-safe counters whose label vocabulary is deliberately bounded."""

    def __init__(self) -> None:
        self._counts: defaultdict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(
        self, name: MetricName, labels: Mapping[str, str] | None = None, value: int = 1
    ) -> None:
        if name not in _METRIC_FAMILIES or not match(_METRIC_RE, name):
            raise ValueError("metric family is not supported")
        if type(value) is not int or value < 1:
            raise ValueError("metric name and increment must be safe")
        normalized = dict(labels or {})
        if any(key not in _ALLOWED_LABELS or not match(_LABEL_RE, key) for key in normalized):
            raise ValueError("metric labels are not in the bounded vocabulary")
        if any(str(label) not in _ALLOWED_VALUES[key] for key, label in normalized.items()):
            raise ValueError("metric label value is not in the bounded vocabulary")
        if any(len(str(label)) > 64 for label in normalized.values()):
            raise ValueError("metric label values are bounded")
        key = (name, tuple(sorted((key, str(value)) for key, value in normalized.items())))
        with self._lock:
            self._counts[key] += value

    def observe_http(self, *, method: str, path: str, status: int) -> None:
        normalized_method = method.upper()
        if normalized_method not in _ALLOWED_VALUES["method"]:
            normalized_method = "OTHER"
        self.inc(
            "event_platform_http_requests_total",
            {
                "method": normalized_method,
                "route": normalize_route(path),
                "status": status_family(status),
            },
        )

    def render(self) -> str:
        families: dict[MetricName, str] = {
            "event_platform_http_requests_total": "HTTP requests handled",
            "event_platform_queue_operations_total": "Queue operations",
            "event_platform_worker_operations_total": "Worker operations",
            "event_platform_mongo_operations_total": "Mongo operations",
            "event_platform_elasticsearch_operations_total": "Elasticsearch operations",
            "event_platform_redis_operations_total": "Redis operations",
            "event_platform_rate_limit_decisions_total": "Rate limit decisions",
            "event_platform_lifecycle_events_total": "Lifecycle events",
        }
        with self._lock:
            counts = dict(self._counts)
        lines: list[str] = []
        for name, help_text in families.items():
            lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} counter"))
            for (metric, labels), count in sorted(counts.items()):
                if metric != name:
                    continue
                suffix = (
                    ""
                    if not labels
                    else "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in labels) + "}"
                )
                lines.append(f"{name}{suffix} {count}")
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
