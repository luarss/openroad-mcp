"""Structured logging configuration for OpenROAD MCP server."""

import json
import logging
import sys
from datetime import datetime
from typing import Any

from .config import config


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
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
                "getMessage",
            }:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


class TextFormatter(logging.Formatter):
    """Enhanced text formatter with consistent structure."""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def setup_logging(
    log_level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
) -> logging.Logger:
    """Setup structured logging for the application."""

    # Use config defaults if not provided
    level = log_level or config.log_level
    format_type = log_format or config.log_format
    file_path = log_file or config.log_file

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Choose formatter
    formatter: logging.Formatter
    if format_type.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if file_path:
        file_handler = logging.FileHandler(file_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Get application logger
    logger = logging.getLogger("openroad_mcp")

    # Log configuration
    logger.info(
        "Logging configured",
        extra={
            "log_level": level,
            "log_format": format_type,
            "log_file": file_path,
        },
    )

    return logger
