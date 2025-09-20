"""Interactive session management with PTY and async I/O."""

import asyncio
import time
from datetime import datetime

import psutil

from ..core.models import InteractiveExecResult, InteractiveSessionInfo, SessionState
from ..utils.logging import get_logger
from .buffer import CircularBuffer
from .models import (
    PTYError,
    SessionError,
    SessionTerminatedError,
)
from .pty_handler import PTYHandler

logger = get_logger("interactive_session")


class InteractiveSession:
    """Manages a single PTY-based OpenROAD session with async I/O."""

    def __init__(self, session_id: str, buffer_size: int = 128 * 1024) -> None:
        """Initialize interactive session."""
        self.session_id = session_id
        self.created_at = datetime.now()
        self.command_count = 0
        self.state = SessionState.CREATING

        # Command history and performance tracking
        self.command_history: list[dict] = []
        self.last_activity = datetime.now()
        self.total_cpu_time = 0.0
        self.peak_memory_mb = 0.0
        self.total_commands_executed = 0
        self.session_timeout_seconds: float | None = None

        # Performance metrics
        self._start_time = time.time()
        self._last_memory_check = time.time()

        # Core components
        self.pty = PTYHandler()
        self.output_buffer = CircularBuffer(max_size=buffer_size)
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)

        # Background tasks
        self._reader_task: asyncio.Task | None = None
        self._writer_task: asyncio.Task | None = None
        self._exit_monitor_task: asyncio.Task | None = None

        # Synchronization
        self._shutdown_event = asyncio.Event()

        logger.info(f"Created interactive session {session_id}")

    async def __aenter__(self) -> "InteractiveSession":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
    ) -> None:
        """Async context manager exit with guaranteed cleanup."""
        await self.cleanup()

    async def start(
        self,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        """Start the OpenROAD session."""
        if self.state != SessionState.CREATING:
            raise SessionError(f"Cannot start session in state {self.state.value}", self.session_id)

        try:
            # Default to OpenROAD command
            if command is None:
                command = ["openroad", "-no_init"]

            # Create PTY session
            await self.pty.create_session(command, env, cwd)
            self.state = SessionState.ACTIVE

            # Start background I/O tasks
            self._reader_task = asyncio.create_task(self._read_output())
            self._writer_task = asyncio.create_task(self._write_input())
            self._exit_monitor_task = asyncio.create_task(self._monitor_exit())

            logger.info(f"Started session {self.session_id} with command: {' '.join(command)}")

        except Exception as e:
            self.state = SessionState.ERROR
            await self.cleanup()
            raise SessionError(f"Failed to start session: {e}", self.session_id) from e

    async def send_command(self, command: str) -> None:
        """Send command to the session."""
        if not self.is_alive():
            raise SessionTerminatedError(f"Session {self.session_id} is not active", self.session_id)

        try:
            # Record command in history
            command_entry = {
                "command": command.strip(),
                "timestamp": datetime.now().isoformat(),
                "command_number": self.command_count + 1,
                "execution_start": time.time(),
            }
            self.command_history.append(command_entry)

            # Add newline if not present
            if not command.endswith("\n"):
                command += "\n"

            await self.input_queue.put(command.encode("utf-8"))
            self.command_count += 1
            self.total_commands_executed += 1
            self.last_activity = datetime.now()

            logger.debug(f"Queued command {self.command_count} for session {self.session_id}: {command.strip()}")

        except Exception as e:
            raise SessionError(f"Failed to send command: {e}", self.session_id) from e

    async def read_output(self, timeout_ms: int = 1000) -> InteractiveExecResult:
        """Collect output with timeout."""
        if not self.is_alive():
            raise SessionTerminatedError(f"Session {self.session_id} is not active", self.session_id)

        timeout_s = timeout_ms / 1000.0
        start_time = asyncio.get_event_loop().time()
        collected_chunks: list[bytes] = []

        try:
            while (asyncio.get_event_loop().time() - start_time) < timeout_s:
                # Drain current buffer
                chunks = await self.output_buffer.drain_all()
                if chunks:
                    collected_chunks.extend(chunks)

                # If we have data and no new data for completion window, consider complete
                if collected_chunks:
                    remaining_time = timeout_s - (asyncio.get_event_loop().time() - start_time)
                    completion_window = min(0.1, remaining_time)  # 100ms or remaining time

                    if completion_window > 0:
                        data_arrived = await self.output_buffer.wait_for_data(completion_window)
                        if not data_arrived:
                            break  # No new data, command likely complete
                else:
                    # Wait for any data
                    remaining_time = timeout_s - (asyncio.get_event_loop().time() - start_time)
                    if remaining_time <= 0:
                        break

                    data_arrived = await self.output_buffer.wait_for_data(remaining_time)
                    if not data_arrived:
                        break  # Timeout waiting for data

            # Convert chunks to string
            output = self.output_buffer.to_string(collected_chunks, errors="replace")
            execution_time = asyncio.get_event_loop().time() - start_time
            buffer_size = await self.output_buffer.get_size()

            # Update command history with execution time if we have a recent command
            if self.command_history and "execution_time" not in self.command_history[-1]:
                self.command_history[-1]["execution_time"] = execution_time
                self.command_history[-1]["output_length"] = len(output)

            # Update performance metrics
            await self._update_performance_metrics()
            self.last_activity = datetime.now()

            result = InteractiveExecResult(
                output=output,
                session_id=self.session_id,
                timestamp=datetime.now().isoformat(),
                execution_time=execution_time,
                command_count=self.command_count,
                buffer_size=buffer_size,
            )

            logger.debug(f"Read {len(output)} chars from session {self.session_id} in {execution_time:.3f}s")

            return result

        except Exception as e:
            raise SessionError(f"Failed to read output: {e}", self.session_id) from e

    def is_alive(self) -> bool:
        """Check if session is active and process is running."""
        return self.state == SessionState.ACTIVE and self.pty.is_process_alive()

    async def get_info(self) -> InteractiveSessionInfo:
        """Get session information."""
        uptime = (datetime.now() - self.created_at).total_seconds()
        buffer_size = await self.output_buffer.get_size()

        return InteractiveSessionInfo(
            session_id=self.session_id,
            created_at=self.created_at.isoformat(),
            is_alive=self.is_alive(),
            command_count=self.command_count,
            buffer_size=buffer_size,
            uptime_seconds=uptime,
            state=self.state,
        )

    async def terminate(self, force: bool = False) -> None:
        """Terminate the session."""
        if self.state == SessionState.TERMINATED:
            return

        logger.info(f"Terminating session {self.session_id} (force={force})")

        self.state = SessionState.TERMINATED
        self._shutdown_event.set()

        # Terminate PTY process
        await self.pty.terminate_process(force)

        # Wait for background tasks to complete
        await self._wait_for_tasks()

        logger.info(f"Session {self.session_id} terminated")

    async def cleanup(self) -> None:
        """Clean up session resources."""
        logger.debug(f"Cleaning up session {self.session_id}")

        if self.state not in (SessionState.TERMINATED, SessionState.ERROR):
            self.state = SessionState.TERMINATED
        self._shutdown_event.set()

        # Cancel and wait for tasks
        await self._wait_for_tasks()

        # Clean up PTY
        await self.pty.cleanup()

        # Clear buffer
        await self.output_buffer.clear()

        logger.debug(f"Session {self.session_id} cleanup completed")

    async def _read_output(self) -> None:
        """Background task to read PTY output."""
        logger.debug(f"Started output reader for session {self.session_id}")

        try:
            while not self._shutdown_event.is_set() and self.pty.is_process_alive():
                try:
                    data = await self.pty.read_output(8192)
                    if data:
                        await self.output_buffer.append(data)
                    else:
                        # No data, wait briefly
                        await asyncio.sleep(0.1)

                except PTYError as e:
                    logger.warning(f"PTY read error in session {self.session_id}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error reading output for session {self.session_id}: {e}")
                    break

        finally:
            logger.debug(f"Output reader ended for session {self.session_id}")

    async def _write_input(self) -> None:
        """Background task to write commands to PTY."""
        logger.debug(f"Started input writer for session {self.session_id}")

        try:
            while not self._shutdown_event.is_set():
                try:
                    # Wait for input with timeout to check shutdown
                    data = await asyncio.wait_for(self.input_queue.get(), timeout=1.0)
                    await self.pty.write_input(data)

                except TimeoutError:
                    continue  # Check shutdown and retry
                except PTYError as e:
                    logger.warning(f"PTY write error in session {self.session_id}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error writing input for session {self.session_id}: {e}")
                    break

        finally:
            logger.debug(f"Input writer ended for session {self.session_id}")

    async def _monitor_exit(self) -> None:
        """Background task to monitor process exit."""
        logger.debug(f"Started exit monitor for session {self.session_id}")

        try:
            # Wait for process to exit
            exit_code = await self.pty.wait_for_exit()
            if exit_code is not None:
                logger.info(f"Process in session {self.session_id} exited with code {exit_code}")
                self.state = SessionState.TERMINATED
                self._shutdown_event.set()

        except Exception as e:
            logger.error(f"Error monitoring exit for session {self.session_id}: {e}")
        finally:
            logger.debug(f"Exit monitor ended for session {self.session_id}")

    async def _wait_for_tasks(self) -> None:
        """Wait for all background tasks to complete with proper error handling."""
        tasks = [self._reader_task, self._writer_task, self._exit_monitor_task]
        active_tasks = [task for task in tasks if task and not task.done()]

        if not active_tasks:
            self._reset_task_references()
            return

        # Cancel all tasks first
        for task in active_tasks:
            if not task.cancelled():
                task.cancel()

        # Wait for all tasks with proper error handling
        try:
            results = await asyncio.wait_for(asyncio.gather(*active_tasks, return_exceptions=True), timeout=5.0)

            # Log any unexpected exceptions (cancellation is expected)
            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    task_name = ["reader", "writer", "exit_monitor"][i]
                    logger.warning(f"Task {task_name} failed during cleanup in session {self.session_id}: {result}")

        except TimeoutError:
            logger.error(f"Critical: Tasks failed to complete within 5s in session {self.session_id}")
            # Force reset even on timeout to prevent resource leaks
        except Exception as e:
            logger.error(f"Unexpected error during task cleanup in session {self.session_id}: {e}")

        self._reset_task_references()

    def _reset_task_references(self) -> None:
        """Reset all task references."""
        self._reader_task = None
        self._writer_task = None
        self._exit_monitor_task = None

    async def get_detailed_metrics(self) -> dict:
        """Get detailed performance and state metrics."""
        await self._update_performance_metrics()
        uptime = (datetime.now() - self.created_at).total_seconds()
        idle_time = (datetime.now() - self.last_activity).total_seconds()
        buffer_size = await self.output_buffer.get_size()

        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "is_alive": self.is_alive(),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "uptime_seconds": uptime,
            "idle_seconds": idle_time,
            "commands": {
                "total_executed": self.total_commands_executed,
                "current_count": self.command_count,
                "history_length": len(self.command_history),
            },
            "performance": {
                "total_cpu_time": self.total_cpu_time,
                "peak_memory_mb": self.peak_memory_mb,
                "current_memory_mb": await self._get_current_memory_usage(),
            },
            "buffer": {
                "current_size": buffer_size,
                "max_size": self.output_buffer.max_size,
                "utilization_percent": (buffer_size / self.output_buffer.max_size) * 100
                if self.output_buffer.max_size > 0
                else 0,
            },
            "timeout": {
                "configured_seconds": self.session_timeout_seconds,
                "is_timed_out": await self._check_session_timeout(),
            },
        }

    async def get_command_history(self, limit: int | None = None, search: str | None = None) -> list[dict]:
        """Get command history with optional filtering."""
        history = self.command_history.copy()

        # Filter by search string if provided
        if search:
            history = [cmd for cmd in history if search.lower() in cmd["command"].lower()]

        # Sort by timestamp (most recent first)
        history.sort(key=lambda x: x["timestamp"], reverse=True)

        # Apply limit
        if limit:
            history = history[:limit]

        return history

    async def replay_command(self, command_number: int) -> str:
        """Replay a command from history."""
        # Find command by number
        for cmd in self.command_history:
            if cmd["command_number"] == command_number:
                await self.send_command(cmd["command"])
                return str(cmd["command"])

        raise SessionError(f"Command {command_number} not found in history", self.session_id)

    def set_timeout(self, timeout_seconds: float) -> None:
        """Set session timeout."""
        self.session_timeout_seconds = timeout_seconds
        logger.info(f"Set timeout for session {self.session_id}: {timeout_seconds}s")

    async def is_idle_timeout(self, idle_threshold_seconds: float = 300) -> bool:
        """Check if session has been idle too long."""
        idle_time = (datetime.now() - self.last_activity).total_seconds()
        return idle_time > idle_threshold_seconds

    async def filter_output(self, pattern: str, max_lines: int = 1000) -> list[str]:
        """Filter recent output by pattern."""
        import re

        # Get recent buffer content
        chunks = await self.output_buffer.peek_all()
        if not chunks:
            return []

        # Convert to text and split into lines
        text = self.output_buffer.to_string(chunks, errors="replace")
        lines = text.split("\n")

        # Filter lines
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            matching_lines = [line for line in lines if regex.search(line)]
        except re.error:
            # Fallback to simple string search
            matching_lines = [line for line in lines if pattern.lower() in line.lower()]

        return matching_lines[-max_lines:] if matching_lines else []

    async def _update_performance_metrics(self) -> None:
        """Update performance metrics from system."""
        try:
            if self.pty.process and self.pty.process.pid:
                try:
                    process = psutil.Process(self.pty.process.pid)

                    # Update CPU time
                    cpu_times = process.cpu_times()
                    self.total_cpu_time = cpu_times.user + cpu_times.system

                    # Update memory usage
                    memory_info = process.memory_info()
                    current_memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
                    self.peak_memory_mb = max(self.peak_memory_mb, current_memory_mb)

                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    # Process may not exist or we don't have access
                    pass
        except Exception as e:
            logger.debug(f"Error updating performance metrics for session {self.session_id}: {e}")

    async def _get_current_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            if self.pty.process and self.pty.process.pid:
                try:
                    process = psutil.Process(self.pty.process.pid)
                    memory_info = process.memory_info()
                    return float(memory_info.rss / (1024 * 1024))  # Convert to MB
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass
        except Exception:
            pass
        return 0.0

    async def _check_session_timeout(self) -> bool:
        """Check if session has exceeded configured timeout."""
        if self.session_timeout_seconds is None:
            return False

        uptime = (datetime.now() - self.created_at).total_seconds()
        return uptime > self.session_timeout_seconds
