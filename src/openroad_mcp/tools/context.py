"""Context management tools."""

from ..core.models import CommandHistoryResult, ContextInfo, ProcessState, ProcessStatus
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("context_tools")


class GetCommandHistoryTool(BaseTool):
    """Tool to get command history."""

    async def execute(self) -> str:
        """Get the command history from the OpenROAD session."""
        try:
            history = CommandHistoryResult(
                total_commands=len(self.manager.command_history),
                commands=[cmd.model_dump() for cmd in self.manager.command_history],
            )
            return self._format_result(history)
        except Exception as e:
            logger.exception("Failed to get command history")
            return self._format_result(
                CommandHistoryResult(
                    total_commands=0,
                    commands=[],
                    error=f"Failed to retrieve command history: {str(e)}",
                )
            )


class GetContextTool(BaseTool):
    """Tool to get comprehensive context information."""

    async def execute(self) -> str:
        """Get comprehensive context information including status, recent output, and command history."""
        try:
            context = await self.manager.get_context()
            return self._format_result(context)
        except Exception as e:
            logger.exception("Failed to get context information")
            return self._format_result(
                ContextInfo(
                    status=ProcessStatus(state=ProcessState.ERROR, buffer_stdout_size=0, buffer_stderr_size=0),
                    recent_stdout=[],
                    recent_stderr=[],
                    command_count=0,
                    last_commands=[],
                    error=f"Failed to retrieve context: {str(e)}",
                )
            )
