"""Custom exceptions for OpenROAD MCP server."""


class OpenROADError(Exception):
    """Base exception for OpenROAD-related errors."""

    pass


class ProcessNotRunningError(OpenROADError):
    """Raised when attempting to interact with a non-running process."""

    pass


class ProcessStartupError(OpenROADError):
    """Raised when OpenROAD process fails to start."""

    pass


class ProcessShutdownError(OpenROADError):
    """Raised when OpenROAD process fails to shutdown gracefully."""

    pass


class CommandExecutionError(OpenROADError):
    """Raised when command execution fails."""

    pass


class ConfigurationError(OpenROADError):
    """Raised when configuration is invalid."""

    pass
