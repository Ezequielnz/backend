import json
import logging
import logging.config
from typing import Any, Dict

from app.core.config import settings


class StructuredJSONFormatter(logging.Formatter):
    """Emit logs as JSON lines with optional structured context."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
            }:
                continue
            log_record[key] = value

        return json.dumps(log_record, ensure_ascii=False)


_CONFIGURED = False


def configure_logging() -> None:
    """Configure a structured root logger once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = "DEBUG" if settings.DEBUG else "INFO"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": "app.core.logging_config.StructuredJSONFormatter",
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                    "level": log_level,
                }
            },
            "root": {
                "level": log_level,
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn.access": {"level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
            },
        }
    )

    _CONFIGURED = True
