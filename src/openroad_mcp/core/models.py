"""Data models for OpenROAD MCP server."""

from enum import Enum

from pydantic import BaseModel, Field


class ProcessState(Enum):
    """OpenROAD process states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
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
