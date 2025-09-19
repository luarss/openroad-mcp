"""Interactive session management with PTY and async I/O."""

import asyncio
from datetime import datetime

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
        """Initialize interactive session.

        Args:
            session_id: Unique identifier for this session
            buffer_size: Maximum size of output buffer in bytes
        """
        self.session_id = session_id
        self.created_at = datetime.now()
        self.command_count = 0
        self.state = SessionState.CREATING

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

    async def start(
        self,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        """Start the OpenROAD session.

        Args:
            command: Command to execute (defaults to OpenROAD)
            env: Environment variables
            cwd: Working directory
        """
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
        """Send command to the session.

        Args:
            command: Command string to send
        """
        if not self.is_alive():
            raise SessionTerminatedError(f"Session {self.session_id} is not active", self.session_id)

        try:
            # Add newline if not present
            if not command.endswith("\n"):
                command += "\n"

            await self.input_queue.put(command.encode("utf-8"))
            self.command_count += 1

            logger.debug(f"Queued command {self.command_count} for session {self.session_id}: {command.strip()}")

        except Exception as e:
            raise SessionError(f"Failed to send command: {e}", self.session_id) from e

    async def read_output(self, timeout_ms: int = 1000) -> InteractiveExecResult:
        """Collect output with timeout.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Execution result with output and metadata
        """
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
        """Get session information.

        Returns:
            Current session information
        """
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
        """Terminate the session.

        Args:
            force: Whether to force termination
        """
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
                        await asyncio.sleep(0.005)  # 5ms polling

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
        """Wait for all background tasks to complete."""
        tasks = [self._reader_task, self._writer_task, self._exit_monitor_task]
        active_tasks = [task for task in tasks if task and not task.done()]

        if active_tasks:
            # Cancel tasks
            for task in active_tasks:
                task.cancel()

            # Wait for cancellation with timeout
            try:
                await asyncio.wait_for(asyncio.gather(*active_tasks, return_exceptions=True), timeout=2.0)
            except TimeoutError:
                logger.warning(f"Timeout waiting for tasks to complete in session {self.session_id}")

        # Reset task references
        self._reader_task = None
        self._writer_task = None
        self._exit_monitor_task = None
