"""Interactive session manager for handling multiple concurrent OpenROAD sessions."""

import asyncio
import uuid

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
            logger.error(f"Failed to create session {session_id}: {e}")
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

    async def _cleanup_terminated_sessions(self) -> int:
        """Clean up terminated sessions.

        Returns:
            Number of sessions cleaned up
        """
        async with self._cleanup_lock:
            terminated_ids = []

            for session_id, session in self._sessions.items():
                if not session.is_alive():
                    terminated_ids.append(session_id)

            # Clean up terminated sessions
            for session_id in terminated_ids:
                try:
                    session = self._sessions[session_id]
                    await session.cleanup()
                    del self._sessions[session_id]
                    logger.debug(f"Cleaned up terminated session {session_id}")
                except Exception as e:
                    logger.warning(f"Error cleaning up session {session_id}: {e}")

            if terminated_ids:
                logger.info(f"Cleaned up {len(terminated_ids)} terminated sessions")

            return len(terminated_ids)
