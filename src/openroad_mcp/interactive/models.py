"""Data models for interactive shell functionality."""


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
