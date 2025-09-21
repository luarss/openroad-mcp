"""Base classes for MCP tools."""

import json
from abc import ABC, abstractmethod
from typing import Any

from ..core.manager import OpenROADManager
from ..core.models import (
    CommandHistoryResult,
    CommandResult,
    ContextInfo,
    InteractiveExecResult,
    InteractiveSessionInfo,
    InteractiveSessionListResult,
    ProcessRestartResult,
    ProcessStatus,
    SessionHistoryResult,
    SessionInspectionResult,
    SessionMetricsResult,
    SessionTerminationResult,
)


class BaseTool(ABC):
    """Base class for OpenROAD MCP tools."""

    def __init__(self, manager: OpenROADManager) -> None:
        self.manager = manager

    @abstractmethod
    async def execute(self, *args: Any, **kwargs: Any) -> str:
        """Execute the tool and return JSON result."""
        pass

    def _format_result(
        self,
        result: (
            CommandResult
            | ProcessStatus
            | ContextInfo
            | InteractiveExecResult
            | InteractiveSessionInfo
            | InteractiveSessionListResult
            | CommandHistoryResult
            | ProcessRestartResult
            | SessionTerminationResult
            | SessionInspectionResult
            | SessionHistoryResult
            | SessionMetricsResult
        ),
    ) -> str:
        """Format result as JSON string."""
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), indent=2)
        return json.dumps(result, indent=2)
