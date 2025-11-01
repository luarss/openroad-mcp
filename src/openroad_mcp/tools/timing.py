"""Timing analysis MCP tools"""

from ..timing.models import LoadResult, TimingResult, TimingSummary
from ..timing.session import TimingSession
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("timing_tools")


class LoadTimingDesignTool(BaseTool):
    """Tool for loading ODB files for timing analysis"""

    async def execute(self, odb_path: str, sdc_path: str | None = None, session_id: str | None = None) -> str:
        """Load ODB file and SDC constraints"""
        try:
            if session_id is None:
                session_id = await self.manager.create_session()

            interactive_session = self.manager._sessions.get(session_id)
            if not interactive_session:
                return self._format_result(
                    LoadResult(
                        success=False,
                        design_name="",
                        odb_path=odb_path,
                        sdc_path=sdc_path,
                        message="Session not found",
                        error=f"Session not found: {session_id}",
                    )
                )

            timing_session = TimingSession(session_id, interactive_session)

            result = await timing_session.load_odb(odb_path, sdc_path)

            if not hasattr(self.manager, "_timing_sessions"):
                self.manager._timing_sessions = {}  # type: ignore[attr-defined]
            self.manager._timing_sessions[session_id] = timing_session  # type: ignore[attr-defined]

            return self._format_result(result)

        except Exception as e:
            logger.exception(f"Error loading timing design: {e}")
            return self._format_result(
                LoadResult(
                    success=False, design_name="", odb_path=odb_path, sdc_path=sdc_path, message="Error", error=str(e)
                )
            )


class ExecuteTimingQueryTool(BaseTool):
    """Tool for executing timing queries"""

    async def execute(self, command: str, session_id: str | None = None, use_cache: bool = True) -> str:
        """Execute OpenSTA timing command"""
        try:
            if not hasattr(self.manager, "_timing_sessions"):
                return self._format_result(
                    TimingResult(
                        command=command,
                        data={},
                        cached=False,
                        execution_time=0.0,
                        error="No timing sessions available. Load design first.",
                    )
                )

            if session_id is None:
                if not self.manager._timing_sessions:
                    return self._format_result(
                        TimingResult(
                            command=command,
                            data={},
                            cached=False,
                            execution_time=0.0,
                            error="No timing sessions available",
                        )
                    )
                session_id = next(iter(self.manager._timing_sessions.keys()))

            timing_session = self.manager._timing_sessions.get(session_id)
            if not timing_session:
                return self._format_result(
                    TimingResult(
                        command=command,
                        data={},
                        cached=False,
                        execution_time=0.0,
                        error=f"Timing session not found: {session_id}",
                    )
                )

            result = await timing_session.execute_sta_command(command, use_cache)

            return self._format_result(result)

        except Exception as e:
            logger.exception(f"Error executing timing query: {e}")
            return self._format_result(
                TimingResult(command=command, data={}, cached=False, execution_time=0.0, error=str(e))
            )


class GetTimingSummaryTool(BaseTool):
    """Tool for getting timing summary"""

    async def execute(self, session_id: str | None = None) -> str:
        """Get quick timing summary"""
        try:
            if not hasattr(self.manager, "_timing_sessions"):
                return self._format_result(
                    TimingSummary(design_name="No timing sessions available", wns=None, tns=None)
                )

            if session_id is None:
                if not self.manager._timing_sessions:
                    return self._format_result(
                        TimingSummary(design_name="No timing sessions available", wns=None, tns=None)
                    )
                session_id = next(iter(self.manager._timing_sessions.keys()))

            timing_session = self.manager._timing_sessions.get(session_id)
            if not timing_session:
                return self._format_result(
                    TimingSummary(design_name=f"Timing session not found: {session_id}", wns=None, tns=None)
                )

            summary = await timing_session.get_summary()

            return self._format_result(summary)

        except Exception as e:
            logger.exception(f"Error getting timing summary: {e}")
            return self._format_result(TimingSummary(design_name=f"Error: {str(e)}", wns=None, tns=None))
