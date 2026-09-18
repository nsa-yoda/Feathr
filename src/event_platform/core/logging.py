"""Structured JSON logging for service-owned runtime events."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

_HANDLER_MARKER = "_event_platform_json_handler"
_LOGGERS_TO_FORMAT = ("uvicorn", "uvicorn.error", "uvicorn.access")
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_UVICORN_EVENT_PREFIXES = (
    ("Started server process", "server.process_started"),
    ("Waiting for application startup", "server.startup_waiting"),
    ("Application startup complete", "server.startup_complete"),
    ("Shutting down", "server.shutdown_started"),
    ("Waiting for application shutdown", "server.shutdown_waiting"),
    ("Application shutdown complete", "server.shutdown_complete"),
    ("Finished server process", "server.process_finished"),
)


def _event_name(record: logging.LogRecord, message: str) -> str:
    supplied_event = getattr(record, "event", None)
    if supplied_event is not None:
        return str(supplied_event)
    if record.name.startswith("uvicorn"):
        for prefix, event in _UVICORN_EVENT_PREFIXES:
            if message.startswith(prefix):
                return event
        return "server.runtime"
    return "runtime.log"


_EXTRA_FIELDS = (
    "event",
    "request_id",
    "error_type",
    "error_fields",
    "environment",
    "method",
    "path",
    "status",
    "client_addr",
    "request_line",
    "status_code",
)


class JsonLogFormatter(logging.Formatter):
    """Render log records as one safe JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "event_platform",
            "event": _event_name(record, message),
            "logger": record.name,
            "message": message,
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), default=str)


class JsonAccessLogFormatter(JsonLogFormatter):
    """Render Uvicorn access records without logging query-string values."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        match = re.match(
            r'^(?P<client>\S+) - "(?P<method>\S+) (?P<target>\S+) '
            r'HTTP/(?P<http_version>[^\"]+)" (?P<status>\d+)',
            message,
        )
        if match is not None:
            path = urlsplit(match.group("target")).path
            record = logging.makeLogRecord(
                {
                    **record.__dict__,
                    "args": (),
                    "msg": f"{match.group('method')} {path} HTTP/{match.group('http_version')}",
                    "event": "http.access",
                    "client_addr": match.group("client"),
                    "method": match.group("method"),
                    "path": path,
                    "status_code": int(match.group("status")),
                }
            )
        elif "?" in message:
            record = logging.makeLogRecord(
                {**record.__dict__, "args": (), "msg": message.split("?", 1)[0]}
            )
        return super().format(record)


def configure_logging(level: LogLevel) -> None:
    """Configure service and Uvicorn handlers without duplicating output."""

    numeric_level = logging.getLevelNamesMapping()[level]
    formatter = JsonLogFormatter()
    access_formatter = JsonAccessLogFormatter()
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    service_handler = next(
        (handler for handler in root_logger.handlers if getattr(handler, _HANDLER_MARKER, False)),
        None,
    )
    if service_handler is None:
        service_handler = logging.StreamHandler(sys.stderr)
        setattr(service_handler, _HANDLER_MARKER, True)
        root_logger.addHandler(service_handler)
    service_handler.setLevel(numeric_level)
    service_handler.setFormatter(formatter)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    for logger_name in _LOGGERS_TO_FORMAT:
        logger = logging.getLogger(logger_name)
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setFormatter(access_formatter if logger_name == "uvicorn.access" else formatter)
