"""Configuration settings for OpenROAD MCP server."""

import os
from typing import Any

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Configuration settings for the OpenROAD MCP server."""

    # Process management settings
    COMMAND_TIMEOUT: float = Field(default=30.0, description="Default command timeout in seconds")
    COMMAND_COMPLETION_DELAY: float = Field(default=0.1, description="Delay to consider command complete in seconds")

    # Buffer settings
    DEFAULT_BUFFER_SIZE: int = Field(default=128 * 1024, description="Default circular buffer size in bytes (128KB)")

    # Interactive session settings
    MAX_SESSIONS: int = Field(default=50, description="Maximum number of concurrent interactive sessions")
    SESSION_QUEUE_SIZE: int = Field(default=128, description="Maximum size for session input queue")
    SESSION_IDLE_TIMEOUT: float = Field(default=300.0, description="Session idle timeout in seconds (5 minutes)")

    # Performance settings
    READ_CHUNK_SIZE: int = Field(default=8192, description="Chunk size for reading PTY output in bytes")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format string"
    )

    # Security settings
    ALLOWED_COMMANDS: list[str] = Field(
        default=["openroad"],
        description="List of allowed command executables for interactive sessions",
    )
    ENABLE_COMMAND_VALIDATION: bool = Field(
        default=True,
        description="Enable command validation to prevent command injection",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        env_values: dict[str, Any] = {}

        # Map environment variables to settings with type conversion
        env_mapping = {
            "COMMAND_TIMEOUT": ("OPENROAD_COMMAND_TIMEOUT", float),
            "COMMAND_COMPLETION_DELAY": ("OPENROAD_COMMAND_COMPLETION_DELAY", float),
            "DEFAULT_BUFFER_SIZE": ("OPENROAD_DEFAULT_BUFFER_SIZE", int),
            "MAX_SESSIONS": ("OPENROAD_MAX_SESSIONS", int),
            "SESSION_QUEUE_SIZE": ("OPENROAD_SESSION_QUEUE_SIZE", int),
            "SESSION_IDLE_TIMEOUT": ("OPENROAD_SESSION_IDLE_TIMEOUT", float),
            "READ_CHUNK_SIZE": ("OPENROAD_READ_CHUNK_SIZE", int),
            "LOG_LEVEL": ("LOG_LEVEL", str),
            "LOG_FORMAT": ("LOG_FORMAT", str),
        }

        allowed_commands_env = os.getenv("OPENROAD_ALLOWED_COMMANDS")
        if allowed_commands_env:
            env_values["ALLOWED_COMMANDS"] = [cmd.strip() for cmd in allowed_commands_env.split(",")]

        enable_validation_env = os.getenv("OPENROAD_ENABLE_COMMAND_VALIDATION")
        if enable_validation_env is not None:
            env_values["ENABLE_COMMAND_VALIDATION"] = enable_validation_env.lower() in ("true", "1", "yes")

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
