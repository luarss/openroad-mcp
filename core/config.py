"""Configuration management for OpenROAD MCP server."""

import logging

from pydantic import Field
from pydantic_settings import BaseSettings


class OpenROADConfig(BaseSettings):
    # Process configuration
    OPENROAD_BINARY: str = Field(default="openroad", description="Path to OpenROAD binary")
    STARTUP_TIMEOUT: float = Field(default=30.0, description="Timeout for process startup in seconds")
    COMMAND_TIMEOUT: float = Field(default=5.0, description="Default timeout for commands in seconds")
    SHUTDOWN_TIMEOUT: float = Field(default=10.0, description="Timeout for graceful shutdown in seconds")

    # Buffer configuration
    MAX_BUFFER_SIZE: int = Field(default=1000, description="Maximum lines to keep in output buffers")
    OUTPUT_POLLING_INTERVAL: float = Field(default=0.1, description="Interval for polling process output")
    COMMAND_COMPLETION_DELAY: float = Field(default=0.5, description="Delay to wait for command completion")

    # Logging configuration
    LOG_LEVEL: int = Field(default=logging.INFO, description="Logging level")


# Global configuration instance
config = OpenROADConfig()
