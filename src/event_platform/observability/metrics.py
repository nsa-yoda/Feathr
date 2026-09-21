"""Small, dependency-free Prometheus registry with bounded labels."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Mapping
from math import isfinite
from re import match
from typing import Literal, cast

_ROUTE_PATTERNS = (
    ("health_live", "/health/live"),
    ("health_ready", "/health/ready"),
    ("health_components", "/health/components"),
    ("metrics", "/metrics"),
    ("search", "/events/search"),
    ("realtime_stats", "/events/stats/realtime"),
    ("stats", "/events/stats"),
    ("rebuild", "/operations/search-rebuild"),
    ("visualizer", "/operations/visualizer"),
    ("events", "/events"),
)
_LABEL_RE = r"^[a-z][a-z0-9_]{0,31}$"
_METRIC_RE = r"^[a-z][a-z0-9_]{0,127}$"
_ALLOWED_LABELS = frozenset(
    {"method", "route", "status", "component", "backend", "outcome", "operation"}
)
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
            "visualizer",
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
    "backend": frozenset({"local", "redis", "mongo", "elasticsearch", "queue", "cache"}),
    "operation": frozenset(
        {
            "enqueue",
            "receive",
            "delete",
            "change_visibility",
            "dead_letter",
            "process",
            "insert",
            "get",
            "query",
            "aggregate",
            "ensure_indexes",
            "search",
            "index",
            "bulk_index",
            "get_cache",
            "set_cache",
            "realtime_stats",
        }
    ),
    "outcome": frozenset(
        {
            "startup",
            "shutdown",
            "accepted",
            "allowed",
            "queued",
            "denied",
            "degraded",
            "hit",
            "miss",
            "bypass",
            "success",
            "failure",
            "retry",
            "dlq",
            "inserted",
            "duplicate",
            "conflict",
            "decode_failure",
            "processing_error",
            "visibility_renewed",
            "ownership_lost",
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
    "event_platform_cache_operations_total",
    "event_platform_request_latency_seconds",
    "event_platform_worker_processing_latency_seconds",
    "event_platform_mongo_operation_latency_seconds",
    "event_platform_elasticsearch_operation_latency_seconds",
    "event_platform_redis_operation_latency_seconds",
    "event_platform_queue_depth",
    "event_platform_queue_oldest_age_seconds",
    "event_platform_queue_in_flight",
    "event_platform_worker_active",
    "event_platform_projection_lag_seconds",
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
        "event_platform_cache_operations_total",
    }
)

_HISTOGRAM_BUCKETS: dict[str, tuple[float, ...]] = {
    "event_platform_request_latency_seconds": (
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
    "event_platform_worker_processing_latency_seconds": (
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
    "event_platform_mongo_operation_latency_seconds": (
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
    "event_platform_elasticsearch_operation_latency_seconds": (
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
    "event_platform_redis_operation_latency_seconds": (
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
}
_GAUGE_NAMES = frozenset(
    {
        "event_platform_queue_depth",
        "event_platform_queue_oldest_age_seconds",
        "event_platform_queue_in_flight",
        "event_platform_worker_active",
        "event_platform_projection_lag_seconds",
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
    """Thread-safe bounded counters, histograms, and current-state gauges."""

    def __init__(self) -> None:
        self._counts: defaultdict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            dict[str, object],
        ] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._lock = threading.Lock()

    def inc(
        self, name: MetricName, labels: Mapping[str, str] | None = None, value: int = 1
    ) -> None:
        if name not in _METRIC_FAMILIES or not match(_METRIC_RE, name):
            raise ValueError("metric family is not supported")
        if type(value) is not int or value < 1:
            raise ValueError("metric name and increment must be safe")
        normalized = _validated_labels(labels)
        key = (name, tuple(sorted((key, str(value)) for key, value in normalized.items())))
        with self._lock:
            self._counts[key] += value

    def observe_histogram(
        self,
        name: MetricName,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record one bounded observation in seconds using fixed cumulative buckets."""

        buckets = _HISTOGRAM_BUCKETS.get(name)
        if buckets is None or not isfinite(value) or value < 0:
            raise ValueError("histogram observation is invalid")
        normalized = _validated_labels(labels)
        key = (name, tuple(sorted((key, str(label)) for key, label in normalized.items())))
        with self._lock:
            state = self._histograms.get(key)
            if state is None:
                state = {
                    "count": 0,
                    "sum": 0.0,
                    "min": value,
                    "max": value,
                    "buckets": [0] * len(buckets),
                }
                self._histograms[key] = state
            state["count"] = cast(int, state["count"]) + 1
            state["sum"] = cast(float, state["sum"]) + value
            state["min"] = min(cast(float, state["min"]), value)
            state["max"] = max(cast(float, state["max"]), value)
            bucket_counts = state["buckets"]
            assert isinstance(bucket_counts, list)
            for index, boundary in enumerate(buckets):
                if value <= boundary:
                    bucket_counts[index] += 1

    def set_gauge(
        self,
        name: MetricName,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Set a current-state gauge; gauge values replace rather than accumulate."""

        if name not in _GAUGE_NAMES or not isfinite(value) or value < 0:
            raise ValueError("gauge value is invalid")
        normalized = _validated_labels(labels)
        key = (name, tuple(sorted((key, str(label)) for key, label in normalized.items())))
        with self._lock:
            self._gauges[key] = value

    def observe_http(
        self,
        *,
        method: str,
        path: str,
        status: int,
        duration_seconds: float | None = None,
    ) -> None:
        normalized_method = method.upper()
        if normalized_method not in _ALLOWED_VALUES["method"]:
            normalized_method = "OTHER"
        labels = {
            "method": normalized_method,
            "route": normalize_route(path),
            "status": status_family(status),
        }
        self.inc(
            "event_platform_http_requests_total",
            labels,
        )
        if duration_seconds is not None:
            self.observe_histogram(
                "event_platform_request_latency_seconds",
                duration_seconds,
                {"route": normalize_route(path)},
            )

    def increment_cache(self, outcome: str) -> None:
        if outcome not in {"hit", "miss", "bypass"}:
            raise ValueError("cache outcome is invalid")
        self.inc("event_platform_cache_operations_total", {"outcome": outcome})

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
            "event_platform_cache_operations_total": "Cache outcomes",
        }
        with self._lock:
            counts = dict(self._counts)
            histograms = dict(self._histograms)
            gauges = dict(self._gauges)
        lines: list[str] = []
        for family_name, help_text in families.items():
            lines.extend((f"# HELP {family_name} {help_text}", f"# TYPE {family_name} counter"))
            for (metric, labels), count in sorted(counts.items()):
                if metric != family_name:
                    continue
                suffix = (
                    ""
                    if not labels
                    else "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in labels) + "}"
                )
                lines.append(f"{family_name}{suffix} {count}")
        for histogram_name, buckets in _HISTOGRAM_BUCKETS.items():
            lines.extend(
                (
                    f"# HELP {histogram_name} Bounded latency histogram in seconds",
                    f"# TYPE {histogram_name} histogram",
                )
            )
            for (metric, labels), state in sorted(histograms.items()):
                if metric != histogram_name:
                    continue
                assert isinstance(state, dict)
                bucket_counts = state["buckets"]
                assert isinstance(bucket_counts, list)
                for boundary, count in zip(buckets, bucket_counts, strict=True):
                    bucket_labels = (("le", _format_number(boundary)),)
                    lines.append(
                        f"{histogram_name}_bucket{_format_labels(labels, bucket_labels)} {count}"
                    )
                lines.append(
                    f"{histogram_name}_bucket"
                    f"{_format_labels(labels, (('le', '+Inf'),))} "
                    f"{state['count']}"
                )
                lines.append(f"{histogram_name}_count{_format_labels(labels)} {state['count']}")
                lines.append(
                    f"{histogram_name}_sum{_format_labels(labels)} "
                    f"{_format_number(cast(float, state['sum']))}"
                )
                lines.append(
                    f"{histogram_name}_min{_format_labels(labels)} "
                    f"{_format_number(cast(float, state['min']))}"
                )
                lines.append(
                    f"{histogram_name}_max{_format_labels(labels)} "
                    f"{_format_number(cast(float, state['max']))}"
                )
        for gauge_name in sorted(_GAUGE_NAMES):
            lines.extend(
                (
                    f"# HELP {gauge_name} Current bounded runtime state",
                    f"# TYPE {gauge_name} gauge",
                )
            )
            for (metric, labels), value in sorted(gauges.items()):
                if metric == gauge_name:
                    lines.append(f"{gauge_name}{_format_labels(labels)} {_format_number(value)}")
        return "\n".join(lines) + "\n"


def _validated_labels(labels: Mapping[str, str] | None) -> dict[str, str]:
    normalized = dict(labels or {})
    if any(key not in _ALLOWED_LABELS or not match(_LABEL_RE, key) for key in normalized):
        raise ValueError("metric labels are not in the bounded vocabulary")
    if any(str(label) not in _ALLOWED_VALUES[key] for key, label in normalized.items()):
        raise ValueError("metric label value is not in the bounded vocabulary")
    if any(len(str(label)) > 64 for label in normalized.values()):
        raise ValueError("metric label values are bounded")
    return {key: str(value) for key, value in normalized.items()}


def _format_labels(
    labels: tuple[tuple[str, str], ...], extra: tuple[tuple[str, str], ...] = ()
) -> str:
    combined = tuple(sorted((*labels, *extra)))
    if not combined:
        return ""
    return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in combined) + "}"


def _format_number(value: float) -> str:
    return f"{value:.6g}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
