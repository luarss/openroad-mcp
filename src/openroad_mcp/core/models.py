"""Data models for OpenROAD MCP server."""

from enum import Enum

from pydantic import BaseModel, Field


class ProcessState(Enum):
    """OpenROAD process states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class SessionState(Enum):
    """Interactive session states."""

    CREATING = "creating"
    ACTIVE = "active"
    TERMINATED = "terminated"
    ERROR = "error"


class CommandRecord(BaseModel):
    """Record of a command execution."""

    command: str
    timestamp: str
    id: int


class CommandResult(BaseModel):
    """Result of a command execution."""

    status: str
    message: str | None = None
    stdout: list[str] = Field(default_factory=list)
    stderr: list[str] = Field(default_factory=list)
    execution_time: float | None = None
    pid: int | None = None


class ProcessStatus(BaseModel):
    """OpenROAD process status information."""

    state: ProcessState
    pid: int | None = None
    uptime: float | None = None
    command_count: int = 0
    buffer_stdout_size: int = 0
    buffer_stderr_size: int = 0


class ContextInfo(BaseModel):
    """Context information for the current session."""

    status: ProcessStatus
    recent_stdout: list[str] = Field(default_factory=list)
    recent_stderr: list[str] = Field(default_factory=list)
    command_count: int = 0
    last_commands: list[CommandRecord] = Field(default_factory=list)


class InteractiveSessionInfo(BaseModel):
    """Information about an interactive session for MCP tools."""

    session_id: str
    created_at: str
    is_alive: bool
    command_count: int
    buffer_size: int
    uptime_seconds: float | None = None
    state: str | None = None  # String representation of SessionState for JSON compatibility


class InteractiveExecResult(BaseModel):
    """Result from interactive command execution for MCP tools."""

    output: str
    session_id: str | None
    timestamp: str
    execution_time: float
    command_count: int = 0
    buffer_size: int = 0


class InteractiveSessionListResult(BaseModel):
    """Result containing list of interactive sessions."""

    sessions: list[InteractiveSessionInfo] = Field(default_factory=list)
    total_count: int = 0
    active_count: int = 0
