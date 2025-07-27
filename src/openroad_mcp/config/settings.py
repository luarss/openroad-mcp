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

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format string"
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        env_values = {}

        # Map environment variables to settings
        env_mapping = {
            "OPENROAD_BINARY": "OPENROAD_BINARY",
            "COMMAND_TIMEOUT": "OPENROAD_COMMAND_TIMEOUT",
            "SHUTDOWN_TIMEOUT": "OPENROAD_SHUTDOWN_TIMEOUT",
            "OUTPUT_POLLING_INTERVAL": "OPENROAD_OUTPUT_POLLING_INTERVAL",
            "COMMAND_COMPLETION_DELAY": "OPENROAD_COMMAND_COMPLETION_DELAY",
            "MAX_BUFFER_SIZE": "OPENROAD_MAX_BUFFER_SIZE",
            "LOG_LEVEL": "LOG_LEVEL",
            "LOG_FORMAT": "LOG_FORMAT",
        }

        for setting_key, env_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                env_values[setting_key] = env_value

        return cls(**env_values)


# Global settings instance
settings = Settings.from_env()
