"""Configuration management for OpenROAD MCP server."""

from pydantic import Field
from pydantic_settings import BaseSettings


class OpenROADConfig(BaseSettings):
    """Configuration settings for OpenROAD MCP server."""

    # Process configuration
    openroad_binary: str = Field(default="openroad", description="Path to OpenROAD binary")
    startup_timeout: float = Field(default=30.0, description="Timeout for process startup in seconds")
    command_timeout: float = Field(default=5.0, description="Default timeout for commands in seconds")
    shutdown_timeout: float = Field(default=10.0, description="Timeout for graceful shutdown in seconds")

    # Buffer configuration
    max_buffer_size: int = Field(default=1000, description="Maximum lines to keep in output buffers")
    output_polling_interval: float = Field(default=0.1, description="Interval for polling process output")
    command_completion_delay: float = Field(default=0.5, description="Delay to wait for command completion")

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")
    log_file: str | None = Field(default=None, description="Log file path")

    class Config:
        env_prefix = "OPENROAD_"
        case_sensitive = False


# Global configuration instance
config = OpenROADConfig()
