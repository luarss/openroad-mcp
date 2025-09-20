"""OpenROAD process manager."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from ..config.constants import LAST_COMMANDS_COUNT, PROCESS_SHUTDOWN_TIMEOUT, RECENT_OUTPUT_LINES
from ..config.settings import settings
from ..utils.logging import get_logger
from .exceptions import (
    CommandExecutionError,
    ProcessNotRunningError,
    ProcessShutdownError,
    ProcessStartupError,
)
from .models import CommandRecord, CommandResult, ContextInfo, ProcessState, ProcessStatus

if TYPE_CHECKING:
    from ..interactive.session_manager import InteractiveSessionManager


class OpenROADManager:
    """Singleton class to manage OpenROAD subprocess lifecycle."""

    _instance: "OpenROADManager | None" = None

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
            self.command_history: list[CommandRecord] = []
            self.max_buffer_size = settings.MAX_BUFFER_SIZE
            self.initialized = True
            self.logger = get_logger("manager")
            self._process_start_time: float | None = None

            # Interactive session management (lazy initialization)
            self._interactive_manager: InteractiveSessionManager | None = None

    async def start_process(self) -> CommandResult:
        """Start the OpenROAD process."""
        if self.state == ProcessState.RUNNING:
            return CommandResult(status="already_running", message="OpenROAD process is already running")

        try:
            self.state = ProcessState.STARTING
            self.process = await asyncio.create_subprocess_exec(
                settings.OPENROAD_BINARY,
                "-no_splash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            self.state = ProcessState.RUNNING
            self._process_start_time = asyncio.get_event_loop().time()

            # Start background tasks to read stdout/stderr
            asyncio.create_task(self._read_stdout())
            asyncio.create_task(self._read_stderr())

            self.logger.info(f"OpenROAD process started with PID {self.process.pid}")
            return CommandResult(
                status="started", message=f"OpenROAD process started with PID {self.process.pid}", pid=self.process.pid
            )

        except FileNotFoundError as e:
            self.state = ProcessState.ERROR
            error_msg = f"OpenROAD binary not found: {settings.OPENROAD_BINARY}"
            self.logger.error(error_msg)
            raise ProcessStartupError(error_msg) from e
        except Exception as e:
            self.state = ProcessState.ERROR
            error_msg = f"Failed to start OpenROAD process: {str(e)}"
            self.logger.error(error_msg)
            raise ProcessStartupError(error_msg) from e

    async def execute_command(self, command: str, timeout: float | None = None) -> CommandResult:
        """Execute a command in the OpenROAD process."""
        if self.state != ProcessState.RUNNING or not self.process:
            raise ProcessNotRunningError("OpenROAD process is not running")

        try:
            # Use config default timeout if not provided
            actual_timeout = timeout or settings.COMMAND_TIMEOUT

            # Record command in history
            cmd_record = CommandRecord(
                command=command, timestamp=datetime.now().isoformat(), id=len(self.command_history)
            )
            self.command_history.append(cmd_record)

            # Capture initial buffer positions
            initial_stdout_count = len(self.stdout_buffer)
            initial_stderr_count = len(self.stderr_buffer)

            # Send command
            if self.process.stdin:
                self.process.stdin.write(f"{command}\n".encode())
                await self.process.stdin.drain()

            # Wait for output with polling
            start_time = asyncio.get_event_loop().time()
            last_output_time = start_time

            while (asyncio.get_event_loop().time() - start_time) < actual_timeout:
                await asyncio.sleep(settings.OUTPUT_POLLING_INTERVAL)

                # Check if we got new output
                current_stdout_count = len(self.stdout_buffer)
                current_stderr_count = len(self.stderr_buffer)

                if current_stdout_count > initial_stdout_count or current_stderr_count > initial_stderr_count:
                    last_output_time = asyncio.get_event_loop().time()

                # If no new output for completion delay, consider command complete
                if (asyncio.get_event_loop().time() - last_output_time) > settings.COMMAND_COMPLETION_DELAY:
                    break

            # Capture new output since command was sent
            new_stdout = self.stdout_buffer[initial_stdout_count:]
            new_stderr = self.stderr_buffer[initial_stderr_count:]

            execution_time = asyncio.get_event_loop().time() - start_time

            return CommandResult(
                status="executed",
                message=f"Command executed in {execution_time:.2f}s",
                stdout=new_stdout,
                stderr=new_stderr,
                execution_time=execution_time,
                pid=self.process.pid,
            )

        except Exception as e:
            error_msg = f"Failed to execute command '{command}': {str(e)}"
            self.logger.error(error_msg)
            raise CommandExecutionError(error_msg) from e

    async def stop_process(self) -> CommandResult:
        """Stop the OpenROAD process gracefully."""
        if self.state == ProcessState.STOPPED:
            return CommandResult(status="already_stopped", message="OpenROAD process is already stopped")

        if not self.process:
            self.state = ProcessState.STOPPED
            return CommandResult(status="stopped", message="OpenROAD process was not running")

        try:
            # Send exit command
            if self.process.stdin and not self.process.stdin.is_closing():
                self.process.stdin.write(b"exit\n")
                await self.process.stdin.drain()
                self.process.stdin.close()

            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(self.process.wait(), timeout=settings.SHUTDOWN_TIMEOUT)
            except TimeoutError:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=PROCESS_SHUTDOWN_TIMEOUT)

            self.state = ProcessState.STOPPED
            self.process = None
            self._process_start_time = None

            return CommandResult(status="stopped", message="OpenROAD process stopped successfully")

        except Exception as e:
            error_msg = f"Error stopping OpenROAD process: {str(e)}"
            self.logger.error(error_msg)
            raise ProcessShutdownError(error_msg) from e

    async def restart_process(self) -> CommandResult:
        """Restart the OpenROAD process."""
        try:
            if self.state == ProcessState.RUNNING:
                await self.stop_process()

            return await self.start_process()

        except Exception as e:
            error_msg = f"Failed to restart OpenROAD process: {str(e)}"
            self.logger.error(error_msg)
            raise ProcessStartupError(error_msg) from e

    async def get_status(self) -> ProcessStatus:
        """Get the current status of the OpenROAD process."""
        uptime = None
        if self.state == ProcessState.RUNNING and self._process_start_time:
            uptime = asyncio.get_event_loop().time() - self._process_start_time

        return ProcessStatus(
            state=self.state,
            pid=self.process.pid if self.process else None,
            uptime=uptime,
            command_count=len(self.command_history),
            buffer_stdout_size=len(self.stdout_buffer),
            buffer_stderr_size=len(self.stderr_buffer),
        )

    async def get_context(self) -> ContextInfo:
        """Get comprehensive context information."""
        status = await self.get_status()

        # Get recent output
        recent_stdout = self.stdout_buffer[-RECENT_OUTPUT_LINES:] if self.stdout_buffer else []
        recent_stderr = self.stderr_buffer[-RECENT_OUTPUT_LINES:] if self.stderr_buffer else []

        return ContextInfo(
            status=status,
            recent_stdout=recent_stdout,
            recent_stderr=recent_stderr,
            command_count=len(self.command_history),
            last_commands=self.command_history[-LAST_COMMANDS_COUNT:] if self.command_history else [],
        )

    async def _read_stdout(self) -> None:
        """Background task to read stdout."""
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode().strip()
                if line:
                    self.stdout_buffer.append(line)
                    if len(self.stdout_buffer) > self.max_buffer_size:
                        self.stdout_buffer.pop(0)
        except Exception as e:
            self.logger.error(f"Error reading stdout: {e}")

    async def _read_stderr(self) -> None:
        """Background task to read stderr."""
        if not self.process or not self.process.stderr:
            return

        try:
            while True:
                line_bytes = await self.process.stderr.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode().strip()
                if line:
                    self.stderr_buffer.append(line)
                    if len(self.stderr_buffer) > self.max_buffer_size:
                        self.stderr_buffer.pop(0)
        except Exception as e:
            self.logger.error(f"Error reading stderr: {e}")

    @property
    def interactive_manager(self) -> "InteractiveSessionManager":
        """Get or create interactive session manager."""
        if self._interactive_manager is None:
            # Lazy import to avoid circular dependencies
            from ..interactive.session_manager import InteractiveSessionManager

            self._interactive_manager = InteractiveSessionManager()
            self.logger.info("Initialized interactive session manager")
        return self._interactive_manager

    async def cleanup_all(self) -> None:
        """Clean up both subprocess and interactive sessions."""
        self.logger.info("Starting comprehensive OpenROAD cleanup")

        # Clean up interactive sessions first
        if self._interactive_manager is not None:
            try:
                await self._interactive_manager.cleanup()
                self.logger.info("Interactive sessions cleaned up")
            except Exception:
                self.logger.exception("Error cleaning up interactive sessions")

        # Clean up subprocess
        if self.state == ProcessState.RUNNING:
            try:
                await self.stop_process()
                self.logger.info("Subprocess cleaned up")
            except Exception:
                self.logger.exception("Error cleaning up subprocess")

        self.logger.info("Comprehensive OpenROAD cleanup completed")
