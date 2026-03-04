"""Data models for Code Mode results."""

from pydantic import BaseModel, Field


class CommandInfo(BaseModel):
    """Information about an OpenROAD command."""

    name: str
    category: str
    description: str | None = None
    arguments: list[str] | None = None
    is_safe: bool = True


class CodeSearchResult(BaseModel):
    """Result from code_search tool."""

    commands: list[CommandInfo] = Field(default_factory=list)
    categories: list[str] | None = None
    total_matches: int = 0
    query: str
    error: str | None = None


class CodeExecuteResult(BaseModel):
    """Result from code_execute tool."""

    output: str
    session_id: str | None = None
    timestamp: str
    execution_time: float
    command_count: int = 0
    confirmation_required: bool = False
    confirmation_reason: str | None = None
    error: str | None = None
