"""Structured logging configuration for OpenROAD MCP server."""

import logging
import sys

from .config import config


def setup_logging() -> logging.Logger:
    """Setup structured logging for the application."""
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(config.LOG_LEVEL)

    # Console handler
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
