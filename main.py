import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from fastmcp import FastMCP

from core.config import config
from core.logging_config import setup_logging

setup_logging()
mcp: FastMCP = FastMCP("openroad-mcp")


class ProcessState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class OpenROADManager:
    _instance: Optional["OpenROADManager"] = None

    def __new__(cls) -> "OpenROADManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.process: asyncio.subprocess.Process | None = None
            self.state = ProcessState.STOPPED
            self.command_queue: asyncio.Queue = asyncio.Queue()
            self.stdout_buffer: list[str] = []
            self.stderr_buffer: list[str] = []
            self.command_history: list[dict[str, Any]] = []
            self.max_buffer_size = config.max_buffer_size
            self.initialized = True
            self.logger = logging.getLogger(__name__)

    async def start_process(self) -> dict[str, Any]:
        if self.state == ProcessState.RUNNING:
            return {"status": "already_running", "message": "OpenROAD process is already running"}

        try:
            self.state = ProcessState.STARTING
            self.process = await asyncio.create_subprocess_exec(
                config.openroad_binary,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self.state = ProcessState.RUNNING

            # Start background tasks to read stdout/stderr
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())

            self.logger.info("OpenROAD process started successfully")
            return {"status": "started", "pid": self.process.pid, "message": "OpenROAD process started successfully"}

        except FileNotFoundError:
            self.state = ProcessState.ERROR
            error_msg = "OpenROAD binary not found. Please ensure OpenROAD is installed and in PATH."
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        except Exception as e:
            self.state = ProcessState.ERROR
            error_msg = f"Failed to start OpenROAD process: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    async def execute_command(self, command: str, timeout: float | None = None) -> dict[str, Any]:
        if self.state != ProcessState.RUNNING or not self.process:
            return {"status": "error", "message": "OpenROAD process is not running"}

        try:
            # Use config default timeout if not provided
            actual_timeout = timeout or config.command_timeout

            # Record command in history
            cmd_record = {"command": command, "timestamp": datetime.now().isoformat(), "id": len(self.command_history)}
            self.command_history.append(cmd_record)

            # Capture initial buffer positions
            initial_stdout_count = len(self.stdout_buffer)
            initial_stderr_count = len(self.stderr_buffer)

            # Send command to process
            if self.process.stdin:
                self.process.stdin.write(f"{command}\n".encode())
                await self.process.stdin.drain()

            # Wait for output with polling
            start_time = asyncio.get_event_loop().time()
            last_output_time = start_time

            while (asyncio.get_event_loop().time() - start_time) < actual_timeout:
                await asyncio.sleep(config.output_polling_interval)

                # Check if we got new output
                current_stdout_count = len(self.stdout_buffer)
                current_stderr_count = len(self.stderr_buffer)

                if current_stdout_count > initial_stdout_count or current_stderr_count > initial_stderr_count:
                    last_output_time = asyncio.get_event_loop().time()

                # If no new output for 0.5 seconds, consider command complete
                if (asyncio.get_event_loop().time() - last_output_time) > config.command_completion_delay:
                    break

            # Capture new output since command was sent
            new_stdout = self.stdout_buffer[initial_stdout_count:]
            new_stderr = self.stderr_buffer[initial_stderr_count:]

            return {
                "status": "executed",
                "command": command,
                "command_id": cmd_record["id"],
                "message": f"Command '{command}' executed",
                "stdout": new_stdout,
                "stderr": new_stderr,
                "stdout_lines": len(new_stdout),
                "stderr_lines": len(new_stderr),
            }

        except Exception as e:
            error_msg = f"Failed to execute command: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    async def get_output(self, lines: int | None = None) -> dict[str, Any]:
        if lines is None:
            stdout_lines = self.stdout_buffer[:]
            stderr_lines = self.stderr_buffer[:]
        else:
            stdout_lines = self.stdout_buffer[-lines:] if lines > 0 else []
            stderr_lines = self.stderr_buffer[-lines:] if lines > 0 else []

        return {
            "stdout": stdout_lines,
            "stderr": stderr_lines,
            "stdout_count": len(self.stdout_buffer),
            "stderr_count": len(self.stderr_buffer),
        }

    async def get_status(self) -> dict[str, Any]:
        status_info = {
            "state": self.state.value,
            "pid": self.process.pid if self.process else None,
            "commands_executed": len(self.command_history),
            "stdout_lines": len(self.stdout_buffer),
            "stderr_lines": len(self.stderr_buffer),
        }

        if self.process:
            status_info["process_alive"] = self.process.returncode is None
            if self.process.returncode is not None:
                status_info["return_code"] = self.process.returncode

        return status_info

    async def stop_process(self) -> dict[str, Any]:
        if self.state == ProcessState.STOPPED or not self.process:
            return {"status": "already_stopped", "message": "OpenROAD process is not running"}

        try:
            # Send exit command
            if self.process.stdin and not self.process.stdin.is_closing():
                self.process.stdin.write(b"exit\n")
                await self.process.stdin.drain()
                self.process.stdin.close()

            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(self.process.wait(), timeout=config.shutdown_timeout)
            except TimeoutError:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=2.0)

            self.state = ProcessState.STOPPED
            self.process = None

            return {"status": "stopped", "message": "OpenROAD process stopped successfully"}

        except Exception as e:
            error_msg = f"Error stopping process: {str(e)}"
            self.logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    async def restart_process(self) -> dict[str, Any]:
        stop_result = await self.stop_process()
        if stop_result["status"] in ["stopped", "already_stopped"]:
            return await self.start_process()
        else:
            return {"status": "error", "message": f"Failed to stop process: {stop_result['message']}"}

    async def _read_stdout(self) -> None:
        if not self.process or not self.process.stdout:
            return

        try:
            async for line_bytes in self.process.stdout:
                line = line_bytes.decode().strip()
                if line:
                    self.stdout_buffer.append(line)
                    if len(self.stdout_buffer) > self.max_buffer_size:
                        self.stdout_buffer.pop(0)
        except Exception as e:
            self.logger.error(f"Error reading stdout: {e}")

    async def _read_stderr(self) -> None:
        if not self.process or not self.process.stderr:
            return

        try:
            async for line_bytes in self.process.stderr:
                line = line_bytes.decode().strip()
                if line:
                    self.stderr_buffer.append(line)
                    if len(self.stderr_buffer) > self.max_buffer_size:
                        self.stderr_buffer.pop(0)
        except Exception as e:
            self.logger.error(f"Error reading stderr: {e}")


# Global manager instance
manager = OpenROADManager()


@mcp.tool()
async def start_openroad() -> str:
    """Start the OpenROAD interactive process in the background."""
    result = await manager.start_process()
    return json.dumps(result, indent=2)


@mcp.tool()
async def execute_openroad_command(command: str, timeout: float | None = None) -> str:
    """Execute a command in the OpenROAD interactive process and return the output."""
    result = await manager.execute_command(command, timeout)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_openroad_status() -> str:
    """Get the current status of the OpenROAD process."""
    result = await manager.get_status()
    return json.dumps(result, indent=2)


@mcp.tool()
async def stop_openroad() -> str:
    """Stop the OpenROAD interactive process."""
    result = await manager.stop_process()
    return json.dumps(result, indent=2)


@mcp.tool()
async def restart_openroad() -> str:
    """Restart the OpenROAD interactive process."""
    result = await manager.restart_process()
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_command_history() -> str:
    """Get the history of commands executed in the OpenROAD process."""
    return json.dumps(manager.command_history, indent=2)


# Context information available through get_openroad_context tool
@mcp.tool()
async def get_openroad_context() -> str:
    """Get OpenROAD session context including process state and recent output stored as session variables."""
    status = await manager.get_status()
    recent_output = await manager.get_output(10)  # Last 10 lines

    context = {
        "openroad_status": status,
        "recent_stdout": recent_output["stdout"],
        "recent_stderr": recent_output["stderr"],
        "command_count": len(manager.command_history),
        "last_commands": manager.command_history[-5:] if manager.command_history else [],
    }
    return json.dumps(context, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
