"""Context management tools."""

from .base import BaseTool


class GetCommandHistoryTool(BaseTool):
    """Tool to get command history."""

    async def execute(self) -> str:
        """Get the command history from the OpenROAD session."""
        history = {
            "total_commands": len(self.manager.command_history),
            "commands": [cmd.model_dump() for cmd in self.manager.command_history],
        }
        return self._format_result(history)


class GetContextTool(BaseTool):
    """Tool to get comprehensive context information."""

    async def execute(self) -> str:
        """Get comprehensive context information including status, recent output, and command history."""
        context = await self.manager.get_context()
        return self._format_result(context)
