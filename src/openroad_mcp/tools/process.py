"""Process management tools."""

from ..core.exceptions import CommandExecutionError, ProcessNotRunningError, ProcessStartupError
from ..core.models import CommandResult, ProcessRestartResult, ProcessState, ProcessStatus
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("process_tools")


class ExecuteCommandTool(BaseTool):
    """Tool to execute commands in OpenROAD process."""

    async def execute(self, command: str, timeout: float | None = None) -> str:
        """Execute a command in the OpenROAD interactive process and return the output."""
        try:
            result = await self.manager.execute_command(command, timeout)
            return self._format_result(result)
        except ProcessNotRunningError as e:
            logger.warning(f"Process not running for command: {command}")
            return self._format_result(
                CommandResult(
                    status="error",
                    message=f"OpenROAD process is not running: {str(e)}",
                    command=command,
                    error=str(e),
                )
            )
        except CommandExecutionError as e:
            logger.error(f"Command execution failed: {command}")
            return self._format_result(
                CommandResult(
                    status="error",
                    message=f"Command execution failed: {str(e)}",
                    command=command,
                    error=str(e),
                )
            )
        except Exception as e:
            logger.exception(f"Unexpected error executing command: {command}")
            return self._format_result(
                CommandResult(
                    status="error",
                    message=f"Unexpected error occurred: {str(e)}",
                    command=command,
                    error=str(e),
                )
            )


class GetStatusTool(BaseTool):
    """Tool to get OpenROAD process status."""

    async def execute(self) -> str:
        """Get the current status of the OpenROAD process."""
        try:
            result = await self.manager.get_status()
            return self._format_result(result)
        except Exception as e:
            logger.exception("Failed to get process status")
            return self._format_result(
                ProcessStatus(
                    state=ProcessState.ERROR,
                    buffer_stdout_size=0,
                    buffer_stderr_size=0,
                    message=f"Failed to get status: {str(e)}",
                    error=str(e),
                )
            )


class RestartProcessTool(BaseTool):
    """Tool to restart OpenROAD process."""

    async def execute(self) -> str:
        """Restart the OpenROAD interactive process."""
        try:
            result = await self.manager.restart_process()
            return self._format_result(result)
        except ProcessStartupError as e:
            logger.error(f"Process restart failed: {e}")
            return self._format_result(
                ProcessRestartResult(
                    status="error",
                    message=f"Process restart failed: {str(e)}",
                    error=str(e),
                )
            )
        except Exception as e:
            logger.exception("Unexpected error during process restart")
            return self._format_result(
                ProcessRestartResult(
                    status="error",
                    message=f"Restart failed with unexpected error: {str(e)}",
                    error=str(e),
                )
            )
