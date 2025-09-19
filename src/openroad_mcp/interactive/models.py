"""Data models for interactive shell functionality."""

from enum import Enum

from pydantic import BaseModel


class SessionState(Enum):
    """Interactive session states."""

    CREATING = "creating"
    ACTIVE = "active"
    TERMINATED = "terminated"
    ERROR = "error"


class InteractiveSessionInfo(BaseModel):
    """Information about an interactive session."""

    session_id: str
    created_at: str
    state: SessionState
    is_alive: bool
    command_count: int
    buffer_size: int
    uptime_seconds: float | None = None


class InteractiveExecResult(BaseModel):
    """Result from interactive command execution."""

    output: str
    session_id: str | None
    timestamp: str
    execution_time: float
    command_count: int = 0
    buffer_size: int = 0


class SessionError(Exception):
    """Base exception for session-related errors."""

    def __init__(self, message: str, session_id: str | None = None):
        super().__init__(message)
        self.session_id = session_id


class SessionNotFoundError(SessionError):
    """Raised when a session ID is not found."""

    pass


class SessionTerminatedError(SessionError):
    """Raised when attempting to use a terminated session."""

    pass


class PTYError(Exception):
    """Raised when PTY operations fail."""

    pass
