"""Process management tools."""

from .base import BaseTool


class ExecuteCommandTool(BaseTool):
    """Tool to execute commands in OpenROAD process."""

    async def execute(self, command: str, timeout: float | None = None) -> str:
        """Execute a command in the OpenROAD interactive process and return the output."""
        result = await self.manager.execute_command(command, timeout)
        return self._format_result(result)


class GetStatusTool(BaseTool):
    """Tool to get OpenROAD process status."""

    async def execute(self) -> str:
        """Get the current status of the OpenROAD process."""
        result = await self.manager.get_status()
        return self._format_result(result)


class RestartProcessTool(BaseTool):
    """Tool to restart OpenROAD process."""

    async def execute(self) -> str:
        """Restart the OpenROAD interactive process."""
        result = await self.manager.restart_process()
        return self._format_result(result)
