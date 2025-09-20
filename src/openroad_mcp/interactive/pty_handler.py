"""PTY (pseudo-terminal) handler for true terminal emulation."""

import asyncio
import errno
import fcntl
import os
import pty
import termios

from ..utils.logging import get_logger
from .models import PTYError

logger = get_logger("pty_handler")


class PTYHandler:
    """Handles PTY creation and I/O operations for terminal emulation."""

    def __init__(self) -> None:
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.process: asyncio.subprocess.Process | None = None
        self._original_attrs: list | None = None

    async def create_session(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        """Create PTY pair and spawn process with terminal emulation."""
        try:
            # Create PTY pair
            self.master_fd, self.slave_fd = pty.openpty()
            logger.debug(f"Created PTY pair: master={self.master_fd}, slave={self.slave_fd}")

            # Configure terminal settings
            self._configure_terminal()

            # Prepare environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)

            # Set terminal environment variables
            process_env.update(
                {
                    "TERM": "xterm-256color",
                    "COLUMNS": "80",
                    "LINES": "24",
                }
            )

            # Create subprocess with slave as stdin/stdout/stderr
            self.process = await asyncio.create_subprocess_exec(
                *command,
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                env=process_env,
                cwd=cwd,
                preexec_fn=os.setsid,  # Create new session
            )

            logger.info(f"Created PTY session with PID {self.process.pid} for command: {' '.join(command)}")

            # Close slave FD in parent - child has its own copy
            if self.slave_fd is not None:
                os.close(self.slave_fd)
                logger.debug(f"Closed slave FD {self.slave_fd} in parent process")
                self.slave_fd = None

        except OSError as e:
            raise PTYError(f"Failed to create PTY session: {e}") from e
        except Exception as e:
            await self.cleanup()
            raise PTYError(f"Unexpected error creating PTY session: {e}") from e

    def _configure_terminal(self) -> None:
        """Configure terminal attributes for optimal OpenROAD interaction."""
        if self.slave_fd is None:
            raise PTYError("Cannot configure terminal: slave_fd is None")

        try:
            # Get current terminal attributes
            self._original_attrs = termios.tcgetattr(self.slave_fd)
            attrs = termios.tcgetattr(self.slave_fd)

            # Configure for raw mode with some cooked features
            # Enable canonical mode for line editing but disable echo
            attrs[3] &= ~termios.ECHO  # Disable echo (we'll handle output)
            attrs[3] |= termios.ICANON  # Enable canonical mode for line editing

            # Set input/output processing
            attrs[0] |= termios.ICRNL  # Map CR to NL on input
            attrs[1] |= termios.OPOST | termios.ONLCR  # Enable output processing

            # Apply changes
            termios.tcsetattr(self.slave_fd, termios.TCSANOW, attrs)

            # Configure master for non-blocking reads
            if self.master_fd is not None:
                flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
                fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            logger.debug("Configured terminal attributes for PTY")

        except (OSError, termios.error) as e:
            raise PTYError(f"Failed to configure terminal: {e}") from e

    async def write_input(self, data: bytes) -> None:
        """Write data to PTY master (goes to process stdin)."""
        if self.master_fd is None:
            raise PTYError("Cannot write: master_fd is None")

        try:
            # Use asyncio thread pool for blocking write
            def _write() -> int:
                assert self.master_fd is not None  # Already checked above
                return os.write(self.master_fd, data)

            await asyncio.to_thread(_write)
            logger.debug(f"Wrote {len(data)} bytes to PTY")

        except (OSError, BrokenPipeError) as e:
            raise PTYError(f"Failed to write to PTY: {e}") from e

    async def read_output(self, size: int = 8192) -> bytes | None:
        """Read data from PTY master (process output)."""
        if self.master_fd is None:
            raise PTYError("Cannot read: master_fd is None")

        try:
            # Use asyncio thread pool for blocking read
            def _read() -> bytes | None:
                try:
                    assert self.master_fd is not None  # Already checked above
                    return os.read(self.master_fd, size)
                except BlockingIOError:
                    return None

            data = await asyncio.to_thread(_read)
            if data:
                logger.debug(f"Read {len(data)} bytes from PTY")
            return data

        except OSError as e:
            if e.errno == errno.EIO:  # EIO - process terminated
                logger.debug("PTY read failed: process terminated")
                return None
            raise PTYError(f"Failed to read from PTY: {e}") from e

    def is_process_alive(self) -> bool:
        """Check if the spawned process is still alive."""
        if self.process is None:
            return False

        return self.process.returncode is None

    async def wait_for_exit(self, timeout: float | None = None) -> int | None:
        """Wait for process to exit and return exit code."""
        if self.process is None:
            return None

        try:
            if timeout:
                await asyncio.wait_for(self.process.wait(), timeout=timeout)
            else:
                await self.process.wait()
            return self.process.returncode
        except TimeoutError:
            return None

    async def terminate_process(self, force: bool = False) -> None:
        """Terminate the spawned process."""
        if self.process is None:
            return

        if not self.is_process_alive():
            logger.debug("Process already terminated")
            return

        try:
            if force:
                # Send SIGKILL for immediate termination
                self.process.kill()
                logger.info(f"Sent SIGKILL to process {self.process.pid}")
            else:
                # Send SIGTERM for graceful termination
                self.process.terminate()
                logger.info(f"Sent SIGTERM to process {self.process.pid}")

                # Wait for graceful shutdown
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    # Force kill if graceful shutdown fails
                    logger.warning("Graceful shutdown timeout, forcing termination")
                    self.process.kill()
                    await self.process.wait()

        except ProcessLookupError:
            # Process already dead
            logger.debug("Process already terminated during termination attempt")

    async def cleanup(self) -> None:
        """Clean up PTY resources and terminate process."""
        logger.debug("Cleaning up PTY handler")

        # Terminate process if running
        if self.process and self.is_process_alive():
            await self.terminate_process()

        # Restore original terminal attributes
        if self.slave_fd is not None and self._original_attrs is not None:
            try:
                termios.tcsetattr(self.slave_fd, termios.TCSANOW, self._original_attrs)
            except (OSError, termios.error):
                pass  # Best effort cleanup

        # Close file descriptors
        for fd in [self.master_fd, self.slave_fd]:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass  # Best effort cleanup

        # Reset state
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self._original_attrs = None

        logger.debug("PTY handler cleanup completed")

    def __del__(self) -> None:
        """Ensure cleanup on garbage collection."""
        # Note: We can't use async cleanup in __del__
        # This is best-effort synchronous cleanup
        if self.master_fd is not None or self.slave_fd is not None:
            for fd in [self.master_fd, self.slave_fd]:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
