"""Structured JSON logging for service-owned runtime events."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_HANDLER_MARKER = "_event_platform_json_handler"
_LOGGERS_TO_FORMAT = ("uvicorn", "uvicorn.error", "uvicorn.access")
_EXTRA_FIELDS = (
    "event",
    "request_id",
    "error_type",
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
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    """Configure service and Uvicorn handlers without duplicating output."""

    numeric_level = logging.getLevelNamesMapping()[level]
    formatter = JsonLogFormatter()
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
            handler.setFormatter(formatter)
