"""Interactive shell tools for OpenROAD MCP server."""

from datetime import datetime

from ..core.models import InteractiveExecResult, InteractiveSessionInfo, InteractiveSessionListResult
from ..interactive.models import SessionError, SessionNotFoundError, SessionTerminatedError
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("interactive_tools")


class InteractiveShellTool(BaseTool):
    """Tool for executing commands in interactive OpenROAD sessions."""

    async def execute(self, command: str, session_id: str | None = None, timeout_ms: int | None = None) -> str:
        """Execute a command in an interactive session."""
        try:
            interactive_manager = self.manager.interactive_manager

            # Create session if not provided
            if session_id is None:
                session_id = await interactive_manager.create_session()

            # Execute command
            result = await interactive_manager.execute_command(session_id, command, timeout_ms)

            return self._format_result(result)

        except SessionNotFoundError as e:
            logger.warning(f"Session not found: {session_id}")
            error_result = InteractiveExecResult(
                output=f"Error: {str(e)}",
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                execution_time=0.0,
            )
            return self._format_result(error_result)

        except (SessionTerminatedError, SessionError) as e:
            logger.error(f"Session error for {session_id}: {e}")
            error_result = InteractiveExecResult(
                output=f"Session Error: {str(e)}",
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                execution_time=0.0,
            )
            return self._format_result(error_result)

        except Exception as e:
            logger.exception(f"Unexpected error executing command in session {session_id}")
            error_result = InteractiveExecResult(
                output=f"Unexpected Error: {str(e)}",
                session_id=session_id,
                timestamp=datetime.now().isoformat(),
                execution_time=0.0,
            )
            return self._format_result(error_result)


class ListSessionsTool(BaseTool):
    """Tool for listing interactive sessions."""

    async def execute(self) -> str:
        """List all interactive sessions."""
        try:
            interactive_manager = self.manager.interactive_manager
            sessions = await interactive_manager.list_sessions()

            # Convert from interactive models to core models
            core_sessions = []
            active_count = 0

            for session in sessions:
                core_session = InteractiveSessionInfo(
                    session_id=session.session_id,
                    created_at=session.created_at,
                    is_alive=session.is_alive,
                    command_count=session.command_count,
                    buffer_size=session.buffer_size,
                    uptime_seconds=session.uptime_seconds,
                    state=session.state,
                )
                core_sessions.append(core_session)
                if session.is_alive:
                    active_count += 1

            result = InteractiveSessionListResult(
                sessions=core_sessions, total_count=len(core_sessions), active_count=active_count
            )

            return self._format_result(result)

        except Exception:
            logger.exception("Failed to list interactive sessions")
            error_result = InteractiveSessionListResult(sessions=[], total_count=0, active_count=0)
            return self._format_result(error_result)


class CreateSessionTool(BaseTool):
    """Tool for creating new interactive sessions."""

    async def execute(
        self,
        session_id: str | None = None,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> str:
        """Create a new interactive session."""
        try:
            interactive_manager = self.manager.interactive_manager

            # Create session
            created_session_id = await interactive_manager.create_session(session_id, command, env, cwd)

            # Get session info
            session_info = await interactive_manager.get_session_info(created_session_id)

            # Convert to core model
            core_session = InteractiveSessionInfo(
                session_id=session_info.session_id,
                created_at=session_info.created_at,
                is_alive=session_info.is_alive,
                command_count=session_info.command_count,
                buffer_size=session_info.buffer_size,
                uptime_seconds=session_info.uptime_seconds,
                state=session_info.state,
            )

            return self._format_result(core_session)

        except SessionError as e:
            logger.error(f"Session creation error: {e}")
            error_result = InteractiveSessionInfo(
                session_id=session_id or "unknown",
                created_at=datetime.now().isoformat(),
                is_alive=False,
                command_count=0,
                buffer_size=0,
            )
            return self._format_result({"error": str(e), "session": error_result.model_dump()})

        except Exception as e:
            logger.exception(f"Unexpected error creating session {session_id}")
            error_result = InteractiveSessionInfo(
                session_id=session_id or "unknown",
                created_at=datetime.now().isoformat(),
                is_alive=False,
                command_count=0,
                buffer_size=0,
            )
            return self._format_result({"error": f"Unexpected error: {str(e)}", "session": error_result.model_dump()})


class TerminateSessionTool(BaseTool):
    """Tool for terminating interactive sessions."""

    async def execute(self, session_id: str, force: bool = False) -> str:
        """Terminate an interactive session."""
        try:
            interactive_manager = self.manager.interactive_manager

            # Get session info before termination
            try:
                session_info = await interactive_manager.get_session_info(session_id)
                was_alive = session_info.is_alive
            except SessionNotFoundError:
                was_alive = False

            # Terminate session
            await interactive_manager.terminate_session(session_id, force)

            result = {"session_id": session_id, "terminated": True, "was_alive": was_alive, "force": force}

            return self._format_result(result)

        except SessionNotFoundError as e:
            logger.warning(f"Attempted to terminate non-existent session: {session_id}")
            result = {"session_id": session_id, "terminated": False, "error": str(e), "force": force}
            return self._format_result(result)

        except Exception as e:
            logger.exception(f"Failed to terminate session {session_id}")
            result = {
                "session_id": session_id,
                "terminated": False,
                "error": f"Unexpected error: {str(e)}",
                "force": force,
            }
            return self._format_result(result)


class InspectSessionTool(BaseTool):
    """Tool for detailed session introspection."""

    async def execute(self, session_id: str) -> str:
        """Get detailed session inspection data."""
        try:
            interactive_manager = self.manager.interactive_manager
            metrics = await interactive_manager.inspect_session(session_id)
            return self._format_result(metrics)

        except SessionNotFoundError as e:
            logger.warning(f"Attempted to inspect non-existent session: {session_id}")
            error_result = {"error": str(e), "session_id": session_id}
            return self._format_result(error_result)

        except Exception as e:
            logger.exception(f"Failed to inspect session {session_id}")
            error_result = {"error": f"Unexpected error: {str(e)}", "session_id": session_id}
            return self._format_result(error_result)


class SessionHistoryTool(BaseTool):
    """Tool for retrieving session command history."""

    async def execute(self, session_id: str, limit: int | None = None, search: str | None = None) -> str:
        """Get command history for a session."""
        try:
            interactive_manager = self.manager.interactive_manager
            history = await interactive_manager.get_session_history(session_id, limit, search)

            result = {
                "session_id": session_id,
                "history": history,
                "total_commands": len(history),
                "limit": limit,
                "search": search,
            }
            return self._format_result(result)

        except SessionNotFoundError as e:
            logger.warning(f"Attempted to get history for non-existent session: {session_id}")
            error_result = {"error": str(e), "session_id": session_id}
            return self._format_result(error_result)

        except Exception as e:
            logger.exception(f"Failed to get history for session {session_id}")
            error_result = {"error": f"Unexpected error: {str(e)}", "session_id": session_id}
            return self._format_result(error_result)


class SessionMetricsTool(BaseTool):
    """Tool for retrieving comprehensive session metrics."""

    async def execute(self) -> str:
        """Get comprehensive metrics for all sessions."""
        try:
            interactive_manager = self.manager.interactive_manager
            metrics = await interactive_manager.session_metrics()
            return self._format_result(metrics)

        except Exception as e:
            logger.exception("Failed to get session metrics")
            error_result = {"error": f"Unexpected error: {str(e)}"}
            return self._format_result(error_result)
