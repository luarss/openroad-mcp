"""Configuration settings for OpenROAD MCP server."""

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Configuration settings for the OpenROAD MCP server."""

    # OpenROAD process settings
    OPENROAD_BINARY: str = Field(default="openroad", description="Path to OpenROAD binary")

    # Process management settings
    COMMAND_TIMEOUT: float = Field(default=30.0, description="Default command timeout in seconds")
    SHUTDOWN_TIMEOUT: float = Field(default=5.0, description="Process shutdown timeout in seconds")
    OUTPUT_POLLING_INTERVAL: float = Field(default=0.01, description="Output polling interval in seconds")
    COMMAND_COMPLETION_DELAY: float = Field(default=0.1, description="Delay to consider command complete in seconds")

    # Buffer settings
    MAX_BUFFER_SIZE: int = Field(default=1000, description="Maximum buffer size for stdout/stderr")
    DEFAULT_BUFFER_SIZE: int = Field(default=128 * 1024, description="Default circular buffer size in bytes (128KB)")
    LARGE_BUFFER_SIZE: int = Field(
        default=10 * 1024 * 1024, description="Large buffer size for testing in bytes (10MB)"
    )

    # Interactive session settings
    MAX_SESSIONS: int = Field(default=50, description="Maximum number of concurrent interactive sessions")
    SESSION_QUEUE_SIZE: int = Field(default=128, description="Maximum size for session input queue")
    SESSION_IDLE_TIMEOUT: float = Field(default=300.0, description="Session idle timeout in seconds (5 minutes)")

    # Performance settings
    READ_CHUNK_SIZE: int = Field(default=8192, description="Chunk size for reading PTY output in bytes")
    WRITE_CHUNK_SIZE: int = Field(default=1024, description="Chunk size for writing data in bytes")
    POLLING_SLEEP_INTERVAL: float = Field(default=0.001, description="Sleep interval during polling in seconds")

    # Memory settings
    DEFAULT_MEMORY_LIMIT_MB: int = Field(default=500, description="Default memory limit in MB")

    # Rate limiting
    RATE_LIMIT_PER_MIN: int = Field(default=60, description="Rate limit per minute")

    # Network settings
    DEFAULT_HTTP_PORT: int = Field(default=8000, description="Default HTTP server port")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format string"
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        env_values = {}

        # Map environment variables to settings with type conversion
        env_mapping = {
            "OPENROAD_BINARY": ("OPENROAD_BINARY", str),
            "COMMAND_TIMEOUT": ("OPENROAD_COMMAND_TIMEOUT", float),
            "SHUTDOWN_TIMEOUT": ("OPENROAD_SHUTDOWN_TIMEOUT", float),
            "OUTPUT_POLLING_INTERVAL": ("OPENROAD_OUTPUT_POLLING_INTERVAL", float),
            "COMMAND_COMPLETION_DELAY": ("OPENROAD_COMMAND_COMPLETION_DELAY", float),
            "MAX_BUFFER_SIZE": ("OPENROAD_MAX_BUFFER_SIZE", int),
            "DEFAULT_BUFFER_SIZE": ("OPENROAD_DEFAULT_BUFFER_SIZE", int),
            "LARGE_BUFFER_SIZE": ("OPENROAD_LARGE_BUFFER_SIZE", int),
            "MAX_SESSIONS": ("OPENROAD_MAX_SESSIONS", int),
            "SESSION_QUEUE_SIZE": ("OPENROAD_SESSION_QUEUE_SIZE", int),
            "SESSION_IDLE_TIMEOUT": ("OPENROAD_SESSION_IDLE_TIMEOUT", float),
            "READ_CHUNK_SIZE": ("OPENROAD_READ_CHUNK_SIZE", int),
            "WRITE_CHUNK_SIZE": ("OPENROAD_WRITE_CHUNK_SIZE", int),
            "POLLING_SLEEP_INTERVAL": ("OPENROAD_POLLING_SLEEP_INTERVAL", float),
            "DEFAULT_MEMORY_LIMIT_MB": ("OPENROAD_DEFAULT_MEMORY_LIMIT_MB", int),
            "RATE_LIMIT_PER_MIN": ("OPENROAD_RATE_LIMIT_PER_MIN", int),
            "DEFAULT_HTTP_PORT": ("OPENROAD_DEFAULT_HTTP_PORT", int),
            "LOG_LEVEL": ("LOG_LEVEL", str),
            "LOG_FORMAT": ("LOG_FORMAT", str),
        }

        for setting_key, (env_key, type_converter) in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                try:
                    env_values[setting_key] = type_converter(env_value)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"Invalid value for {env_key}: {env_value}. Expected {type_converter.__name__}."
                    ) from e

        return cls(**env_values)


# Global settings instance
settings = Settings.from_env()
