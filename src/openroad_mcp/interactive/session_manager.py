"""Interactive session manager for handling multiple concurrent OpenROAD sessions."""

import asyncio
import uuid
from datetime import datetime

from ..core.models import InteractiveExecResult, InteractiveSessionInfo
from ..utils.logging import get_logger
from .models import SessionError, SessionNotFoundError
from .session import InteractiveSession

logger = get_logger("session_manager")


class InteractiveSessionManager:
    """Manages multiple concurrent interactive OpenROAD sessions."""

    def __init__(self, max_sessions: int = 10, default_timeout_ms: int = 10000) -> None:
        """Initialize session manager.

        Args:
            max_sessions: Maximum number of concurrent sessions
            default_timeout_ms: Default timeout for command execution in milliseconds
        """
        self._sessions: dict[str, InteractiveSession] = {}
        self._max_sessions = max_sessions
        self._default_timeout_ms = default_timeout_ms
        self._cleanup_lock = asyncio.Lock()

        logger.info(f"Initialized InteractiveSessionManager with max_sessions={max_sessions}")

    async def create_session(
        self,
        session_id: str | None = None,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> str:
        """Create a new interactive session.

        Args:
            session_id: Optional session ID, generated if not provided
            command: Command to execute (defaults to OpenROAD)
            env: Environment variables
            cwd: Working directory

        Returns:
            The session ID

        Raises:
            SessionError: If session limit exceeded or creation fails
        """
        # Generate session ID if not provided
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        # Check if session already exists
        if session_id in self._sessions:
            raise SessionError(f"Session {session_id} already exists", session_id)

        # Check session limit
        await self._cleanup_terminated_sessions()
        active_count = len([s for s in self._sessions.values() if s.is_alive()])
        if active_count >= self._max_sessions:
            raise SessionError(
                f"Maximum session limit reached ({self._max_sessions}). Currently {active_count} active sessions."
            )

        try:
            # Create and start session
            session = InteractiveSession(session_id)
            await session.start(command, env, cwd)

            self._sessions[session_id] = session
            logger.info(f"Created session {session_id}, total sessions: {len(self._sessions)}")

            return session_id

        except Exception as e:
            logger.exception(f"Failed to create session {session_id}")
            raise SessionError(f"Failed to create session: {e}", session_id) from e

    async def execute_command(
        self, session_id: str, command: str, timeout_ms: int | None = None
    ) -> InteractiveExecResult:
        """Execute a command in the specified session.

        Args:
            session_id: Target session ID
            command: Command to execute
            timeout_ms: Timeout in milliseconds, uses default if not provided

        Returns:
            Execution result with output and metadata

        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionTerminatedError: If session is not active
        """
        session = self._get_session(session_id)
        actual_timeout = timeout_ms or self._default_timeout_ms

        try:
            # Send command and read output
            await session.send_command(command)
            result = await session.read_output(actual_timeout)

            logger.debug(f"Executed command in session {session_id}: {command.strip()}")
            return result

        except Exception as e:
            logger.error(f"Failed to execute command in session {session_id}: {e}")
            raise

    async def get_session_info(self, session_id: str) -> InteractiveSessionInfo:
        """Get information about a specific session.

        Args:
            session_id: Target session ID

        Returns:
            Session information

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        return await session.get_info()

    async def list_sessions(self) -> list[InteractiveSessionInfo]:
        """List all sessions with their information.

        Returns:
            List of session information
        """
        # Clean up terminated sessions first
        await self._cleanup_terminated_sessions()

        session_infos = []
        for session in self._sessions.values():
            try:
                info = await session.get_info()
                session_infos.append(info)
            except Exception as e:
                logger.warning(f"Failed to get info for session {session.session_id}: {e}")

        return session_infos

    async def terminate_session(self, session_id: str, force: bool = False) -> None:
        """Terminate a specific session.

        Args:
            session_id: Target session ID
            force: Whether to force termination

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)

        try:
            await session.terminate(force)
            logger.info(f"Terminated session {session_id}")

            # Remove from sessions dict after cleanup
            async with self._cleanup_lock:
                if session_id in self._sessions:
                    del self._sessions[session_id]

        except Exception as e:
            logger.error(f"Failed to terminate session {session_id}: {e}")
            raise

    async def terminate_all_sessions(self, force: bool = False) -> int:
        """Terminate all sessions.

        Args:
            force: Whether to force termination

        Returns:
            Number of sessions terminated
        """
        session_ids = list(self._sessions.keys())
        terminated_count = 0

        for session_id in session_ids:
            try:
                await self.terminate_session(session_id, force)
                terminated_count += 1
            except Exception as e:
                logger.error(f"Failed to terminate session {session_id}: {e}")

        logger.info(f"Terminated {terminated_count}/{len(session_ids)} sessions")
        return terminated_count

    async def inspect_session(self, session_id: str) -> dict:
        """Get detailed session inspection data.

        Args:
            session_id: Target session ID

        Returns:
            Detailed session metrics and state

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        return await session.get_detailed_metrics()

    async def get_session_history(
        self, session_id: str, limit: int | None = None, search: str | None = None
    ) -> list[dict]:
        """Get command history for a session.

        Args:
            session_id: Target session ID
            limit: Maximum number of commands to return
            search: Optional search string to filter commands

        Returns:
            List of command history entries

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        return await session.get_command_history(limit, search)

    async def replay_command(self, session_id: str, command_number: int) -> str:
        """Replay a command from session history.

        Args:
            session_id: Target session ID
            command_number: Command number to replay

        Returns:
            The command string that was replayed

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        return await session.replay_command(command_number)

    async def filter_session_output(self, session_id: str, pattern: str, max_lines: int = 1000) -> list[str]:
        """Filter session output by pattern.

        Args:
            session_id: Target session ID
            pattern: Regex pattern or simple string to search for
            max_lines: Maximum number of lines to return

        Returns:
            List of matching lines

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        return await session.filter_output(pattern, max_lines)

    async def set_session_timeout(self, session_id: str, timeout_seconds: float) -> None:
        """Set timeout for a session.

        Args:
            session_id: Target session ID
            timeout_seconds: Timeout in seconds

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self._get_session(session_id)
        session.set_timeout(timeout_seconds)

    async def session_metrics(self) -> dict:
        """Get comprehensive metrics for all sessions.

        Returns:
            Session manager and individual session metrics
        """
        await self._cleanup_terminated_sessions()

        total_sessions = len(self._sessions)
        active_sessions = self.get_active_session_count()
        terminated_sessions = total_sessions - active_sessions

        # Collect session metrics
        session_details = []
        total_commands = 0
        total_cpu_time = 0.0
        total_memory_mb = 0.0

        for session in self._sessions.values():
            try:
                metrics = await session.get_detailed_metrics()
                session_details.append(metrics)
                total_commands += metrics["commands"]["total_executed"]
                total_cpu_time += metrics["performance"]["total_cpu_time"]
                total_memory_mb += metrics["performance"]["current_memory_mb"]
            except Exception as e:
                logger.warning(f"Failed to get metrics for session {session.session_id}: {e}")

        return {
            "manager": {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "terminated_sessions": terminated_sessions,
                "max_sessions": self._max_sessions,
                "utilization_percent": (active_sessions / self._max_sessions) * 100 if self._max_sessions > 0 else 0,
            },
            "aggregate": {
                "total_commands": total_commands,
                "total_cpu_time": total_cpu_time,
                "total_memory_mb": total_memory_mb,
                "avg_memory_per_session": total_memory_mb / active_sessions if active_sessions > 0 else 0,
            },
            "sessions": session_details,
        }

    async def cleanup_idle_sessions(self, idle_threshold_seconds: float = 300, force: bool = False) -> int:
        """Clean up sessions that have been idle too long.

        Args:
            idle_threshold_seconds: Idle timeout threshold
            force: Whether to force termination

        Returns:
            Number of sessions cleaned up
        """
        cleaned_count = 0
        session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            try:
                session = self._sessions[session_id]
                if await session.is_idle_timeout(idle_threshold_seconds):
                    await self.terminate_session(session_id, force)
                    cleaned_count += 1
                    logger.info(f"Cleaned up idle session {session_id}")
            except Exception as e:
                logger.error(f"Error checking idle status for session {session_id}: {e}")

        return cleaned_count

    def get_resource_utilization(self) -> dict:
        """Get current resource utilization statistics.

        Returns:
            Resource utilization metrics
        """
        active_count = self.get_active_session_count()
        total_count = self.get_session_count()

        return {
            "sessions": {
                "active": active_count,
                "total": total_count,
                "max_allowed": self._max_sessions,
                "utilization_percent": (active_count / self._max_sessions) * 100 if self._max_sessions > 0 else 0,
                "available_slots": max(0, self._max_sessions - active_count),
            },
            "resource_limits": {
                "approaching_limit": active_count >= (self._max_sessions * 0.8),  # 80% threshold
                "at_limit": active_count >= self._max_sessions,
            },
        }

    async def cleanup(self) -> None:
        """Clean up all sessions and resources."""
        logger.info("Starting session manager cleanup")

        try:
            await self.terminate_all_sessions(force=True)

            # Final cleanup of any remaining sessions
            async with self._cleanup_lock:
                for session in list(self._sessions.values()):
                    try:
                        await session.cleanup()
                    except Exception as e:
                        logger.warning(f"Error during session cleanup: {e}")

                self._sessions.clear()

            logger.info("Session manager cleanup completed")

        except Exception as e:
            logger.error(f"Error during session manager cleanup: {e}")
            raise

    def get_session_count(self) -> int:
        """Get the current number of sessions."""
        return len(self._sessions)

    def get_active_session_count(self) -> int:
        """Get the number of active sessions."""
        return len([s for s in self._sessions.values() if s.is_alive()])

    def _get_session(self, session_id: str) -> InteractiveSession:
        """Get session by ID, raising error if not found.

        Args:
            session_id: Target session ID

        Returns:
            The session instance

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session {session_id} not found", session_id)

        return self._sessions[session_id]

    async def _cleanup_terminated_sessions(self, force_cleanup_after_seconds: float = 60.0) -> int:
        """Clean up terminated sessions with graceful degradation.

        Args:
            force_cleanup_after_seconds: Force cleanup after this many seconds

        Returns:
            Number of sessions cleaned up
        """
        async with self._cleanup_lock:
            terminated_ids = []
            current_time = datetime.now()

            for session_id, session in self._sessions.items():
                if not session.is_alive():
                    # Check if session has been dead long enough for forced cleanup
                    time_since_death = (current_time - session.last_activity).total_seconds()
                    if time_since_death > force_cleanup_after_seconds:
                        terminated_ids.append((session_id, True))  # Force cleanup
                    else:
                        terminated_ids.append((session_id, False))  # Graceful cleanup

            # Clean up terminated sessions
            cleaned_count = 0
            for session_id, force_cleanup in terminated_ids:
                try:
                    session = self._sessions[session_id]
                    if force_cleanup:
                        logger.warning(f"Force cleaning up session {session_id} after {force_cleanup_after_seconds}s")
                        await session.cleanup()
                    else:
                        await session.cleanup()
                    del self._sessions[session_id]
                    cleaned_count += 1
                    logger.debug(f"Cleaned up terminated session {session_id}")
                except Exception as e:
                    logger.warning(f"Error cleaning up session {session_id}: {e}")
                    # In case of error, still remove from dict to prevent accumulation
                    if session_id in self._sessions:
                        del self._sessions[session_id]
                        cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} terminated sessions")

            return cleaned_count
