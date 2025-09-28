"""Interactive session manager for handling multiple concurrent OpenROAD sessions."""

import asyncio
import uuid
from datetime import datetime

from ..config.settings import settings
from ..core.models import InteractiveExecResult, InteractiveSessionInfo
from ..utils.logging import get_logger
from .models import SessionError, SessionNotFoundError
from .session import InteractiveSession

logger = get_logger("session_manager")


class InteractiveSessionManager:
    """Manages multiple concurrent interactive OpenROAD sessions."""

    def __init__(
        self,
        max_sessions: int = settings.MAX_SESSIONS,
        default_timeout_ms: int = int(settings.COMMAND_TIMEOUT * 1000),
        default_buffer_size: int = settings.DEFAULT_BUFFER_SIZE,
    ) -> None:
        """Initialize session manager."""
        self._sessions: dict[str, InteractiveSession | None] = {}
        self._max_sessions = max_sessions
        self._default_timeout_ms = default_timeout_ms
        self._default_buffer_size = default_buffer_size
        self._cleanup_lock = asyncio.Lock()

        logger.info(f"Initialized InteractiveSessionManager with max_sessions={max_sessions}")

    async def create_session(
        self,
        session_id: str | None = None,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        buffer_size: int | None = None,
    ) -> str:
        """Create a new interactive session."""
        # Generate session ID if not provided
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        # Atomically check session limit and create session to prevent TOCTOU race
        async with self._cleanup_lock:
            await self._cleanup_terminated_sessions()

            # Check if session already exists while holding the lock
            if session_id in self._sessions:
                raise SessionError(f"Session {session_id} already exists", session_id)

            # Count active sessions while holding the lock to prevent races
            # Filter out None placeholders when counting
            active_count = len([s for s in self._sessions.values() if s is not None and s.is_alive()])
            if active_count >= self._max_sessions:
                raise SessionError(
                    f"Maximum session limit reached ({self._max_sessions}). Currently {active_count} active sessions.",
                    session_id,
                )

            # Reserve the slot immediately to prevent TOCTOU
            # Use None as placeholder to indicate slot is being created
            self._sessions[session_id] = None

            try:
                # Create and start session outside the dict but within the lock
                actual_buffer_size = buffer_size or self._default_buffer_size
                session = InteractiveSession(session_id, buffer_size=actual_buffer_size)
                await session.start(command, env, cwd)

                # Replace placeholder with actual session
                self._sessions[session_id] = session
                logger.info(f"Created session {session_id}, total sessions: {len(self._sessions)}")

                return session_id

            except Exception as e:
                # Remove placeholder on failure
                if session_id in self._sessions:
                    del self._sessions[session_id]
                logger.exception(f"Failed to create session {session_id}")
                raise SessionError(f"Failed to create session: {e}", session_id) from e

    async def execute_command(
        self, session_id: str, command: str, timeout_ms: int | None = None
    ) -> InteractiveExecResult:
        """Execute a command in the specified session."""
        session = self._get_session(session_id)
        actual_timeout = timeout_ms or self._default_timeout_ms

        try:
            # Send command and read output
            await session.send_command(command)
            result = await session.read_output(actual_timeout)

            logger.debug(f"Executed command in session {session_id}: {command.strip()}")
            return result

        except Exception:
            logger.exception("Failed to execute command in session %s", session_id)
            raise

    async def get_session_info(self, session_id: str) -> InteractiveSessionInfo:
        """Get information about a specific session."""
        session = self._get_session(session_id)
        return await session.get_info()

    async def list_sessions(self) -> list[InteractiveSessionInfo]:
        """List all sessions with their information."""
        # Clean up terminated sessions first
        await self._cleanup_terminated_sessions_with_lock()

        session_infos = []
        for session in self._sessions.values():
            # Skip None placeholders (sessions being created)
            if session is None:
                continue
            try:
                info = await session.get_info()
                session_infos.append(info)
            except Exception as e:
                logger.warning(f"Failed to get info for session {session.session_id}: {e}")

        return session_infos

    async def terminate_session(self, session_id: str, force: bool = False) -> None:
        """Terminate a specific session."""
        session = self._get_session(session_id)

        try:
            await session.terminate(force)
            await session.cleanup()
            logger.info(f"Terminated session {session_id}")

            # Remove from sessions dict after cleanup
            async with self._cleanup_lock:
                if session_id in self._sessions:
                    del self._sessions[session_id]

        except Exception:
            logger.exception("Failed to terminate session %s", session_id)
            raise

    async def terminate_all_sessions(self, force: bool = False) -> int:
        """Terminate all sessions."""
        session_ids = list(self._sessions.keys())
        terminated_count = 0

        for session_id in session_ids:
            try:
                await self.terminate_session(session_id, force)
                terminated_count += 1
            except Exception:
                logger.exception("Failed to terminate session %s", session_id)

        logger.info(f"Terminated {terminated_count}/{len(session_ids)} sessions")
        return terminated_count

    async def inspect_session(self, session_id: str) -> dict:
        """Get detailed session inspection data."""
        session = self._get_session(session_id)
        return await session.get_detailed_metrics()

    async def get_session_history(
        self, session_id: str, limit: int | None = None, search: str | None = None
    ) -> list[dict]:
        """Get command history for a session."""
        session = self._get_session(session_id)
        return await session.get_command_history(limit, search)

    async def replay_command(self, session_id: str, command_number: int) -> str:
        """Replay a command from session history."""
        session = self._get_session(session_id)
        return await session.replay_command(command_number)

    async def filter_session_output(self, session_id: str, pattern: str, max_lines: int = 1000) -> list[str]:
        """Filter session output by pattern."""
        session = self._get_session(session_id)
        return await session.filter_output(pattern, max_lines)

    async def set_session_timeout(self, session_id: str, timeout_seconds: float) -> None:
        """Set timeout for a session."""
        session = self._get_session(session_id)
        session.set_timeout(timeout_seconds)

    async def session_metrics(self) -> dict:
        """Get comprehensive metrics for all sessions."""
        await self._cleanup_terminated_sessions_with_lock()

        total_sessions = len(self._sessions)
        active_sessions = self.get_active_session_count()
        terminated_sessions = total_sessions - active_sessions

        # Collect session metrics
        session_details = []
        total_commands = 0
        total_cpu_time = 0.0
        total_memory_mb = 0.0

        for session in self._sessions.values():
            # Skip None placeholders
            if session is None:
                continue
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
        """Clean up sessions that have been idle too long."""
        cleaned_count = 0
        session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            try:
                session = self._sessions[session_id]
                # Skip None placeholders
                if session is None:
                    continue
                if await session.is_idle_timeout(idle_threshold_seconds):
                    await self.terminate_session(session_id, force)
                    cleaned_count += 1
                    logger.info(f"Cleaned up idle session {session_id}")
            except Exception:
                logger.exception("Error checking idle status for session %s", session_id)

        return cleaned_count

    def get_resource_utilization(self) -> dict:
        """Get current resource utilization statistics."""
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
                    # Skip None placeholders
                    if session is None:
                        continue
                    try:
                        await session.cleanup()
                    except Exception as e:
                        logger.warning(f"Error during session cleanup: {e}")

                self._sessions.clear()

            logger.info("Session manager cleanup completed")

        except Exception:
            logger.exception("Error during session manager cleanup")
            raise

    def get_session_count(self) -> int:
        """Get the current number of sessions."""
        return len(self._sessions)

    def get_active_session_count(self) -> int:
        """Get the number of active sessions."""
        return len([s for s in self._sessions.values() if s is not None and s.is_alive()])

    def _get_session(self, session_id: str) -> InteractiveSession:
        """Get session by ID, raising error if not found or still being created."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session {session_id} not found", session_id)

        session = self._sessions[session_id]
        if session is None:
            raise SessionError(f"Session {session_id} is still being created", session_id)

        return session

    async def _cleanup_terminated_sessions_with_lock(self, force_cleanup_after_seconds: float = 60.0) -> int:
        """Clean up terminated sessions with lock acquisition."""
        async with self._cleanup_lock:
            return await self._cleanup_terminated_sessions(force_cleanup_after_seconds)

    async def _cleanup_terminated_sessions(self, force_cleanup_after_seconds: float = 60.0) -> int:
        """Clean up terminated sessions with graceful degradation."""
        terminated_ids = []
        current_time = datetime.now()

        for session_id, session in self._sessions.items():
            # Skip None placeholders
            if session is None:
                continue
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
                # Skip None placeholders in cleanup
                if session is None:
                    del self._sessions[session_id]
                    cleaned_count += 1
                    continue

                if force_cleanup:
                    logger.warning(f"Force cleaning up session {session_id} after {force_cleanup_after_seconds}s")
                    try:
                        await session.cleanup()
                    except Exception as cleanup_error:
                        logger.error(f"Force cleanup failed for session {session_id}: {cleanup_error}")
                    finally:
                        del self._sessions[session_id]
                        cleaned_count += 1
                else:
                    await session.cleanup()
                    del self._sessions[session_id]
                    cleaned_count += 1
                    logger.debug(f"Cleaned up terminated session {session_id}")
            except Exception as e:
                logger.error(f"Error during session {session_id} cleanup: {e}")
                # In case of error, still remove from dict to prevent accumulation
                if force_cleanup and session_id in self._sessions:
                    logger.warning(f"Force removing session {session_id} from tracking after cleanup error")
                    del self._sessions[session_id]
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} terminated sessions")

        return cleaned_count
