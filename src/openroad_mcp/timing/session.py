"""Timing analysis session management"""

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..interactive.session import InteractiveSession
from ..utils.logging import get_logger
from .models import LoadResult, TimingResult, TimingSummary
from .parsers import BasicTimingParser

logger = get_logger("timing_session")


class TimingSession:
    """Manages timing analysis on a loaded design"""

    def __init__(self, session_id: str, interactive_session: InteractiveSession):
        self.session_id = session_id
        self.session = interactive_session

        self.design_name: str | None = None
        self.odb_path: Path | None = None
        self.sdc_path: Path | None = None
        self.loaded_at: datetime | None = None

        self._cache: dict[str, TimingResult] = {}

        logger.info(f"Created timing session {session_id}")

    async def load_odb(self, odb_path: Path | str, sdc_path: Path | str | None = None) -> LoadResult:
        """Load ODB file and optionally SDC constraints"""
        odb_path = Path(odb_path)
        sdc_path = Path(sdc_path) if sdc_path else None

        if not odb_path.exists():
            return LoadResult(
                success=False,
                design_name="",
                odb_path=str(odb_path),
                sdc_path=str(sdc_path) if sdc_path else None,
                message="ODB file not found",
                error=f"File does not exist: {odb_path}",
            )

        if sdc_path and not sdc_path.exists():
            return LoadResult(
                success=False,
                design_name="",
                odb_path=str(odb_path),
                sdc_path=str(sdc_path),
                message="SDC file not found",
                error=f"File does not exist: {sdc_path}",
            )

        try:
            await self.session.send_command(f"read_db {odb_path}")
            result = await self.session.read_output(timeout_ms=5000)

            if result.error:
                return LoadResult(
                    success=False,
                    design_name="",
                    odb_path=str(odb_path),
                    sdc_path=str(sdc_path) if sdc_path else None,
                    message="Failed to load ODB",
                    error=result.error,
                )

            if sdc_path:
                await self.session.send_command(f"read_sdc {sdc_path}")
                sdc_result = await self.session.read_output(timeout_ms=3000)

                if sdc_result.error:
                    return LoadResult(
                        success=False,
                        design_name="",
                        odb_path=str(odb_path),
                        sdc_path=str(sdc_path),
                        message="Failed to load SDC",
                        error=sdc_result.error,
                    )

            design_name = odb_path.stem

            self.design_name = design_name
            self.odb_path = odb_path
            self.sdc_path = sdc_path
            self.loaded_at = datetime.now()

            self._cache.clear()

            logger.info(f"Loaded design {design_name} from {odb_path}")

            return LoadResult(
                success=True,
                design_name=design_name,
                odb_path=str(odb_path),
                sdc_path=str(sdc_path) if sdc_path else None,
                message=f"Successfully loaded design {design_name}",
            )

        except Exception as e:
            logger.exception(f"Error loading ODB: {e}")
            return LoadResult(
                success=False,
                design_name="",
                odb_path=str(odb_path),
                sdc_path=str(sdc_path) if sdc_path else None,
                message="Unexpected error during load",
                error=str(e),
            )

    async def execute_sta_command(self, command: str, use_cache: bool = True) -> TimingResult:
        """Execute OpenSTA command with optional caching"""
        if not self.design_name:
            return TimingResult(
                command=command,
                data={},
                cached=False,
                execution_time=0.0,
                error="No design loaded. Use load_odb() first.",
            )

        cache_key = self._generate_cache_key(command)

        if use_cache and cache_key in self._cache:
            logger.debug(f"Cache hit for command: {command}")
            cached_result = self._cache[cache_key]
            return TimingResult(
                command=cached_result.command,
                data=cached_result.data,
                cached=True,
                execution_time=cached_result.execution_time,
                timestamp=datetime.now().isoformat(),
                error=cached_result.error,
            )

        try:
            start_time = time.time()

            await self.session.send_command(command)
            result = await self.session.read_output(timeout_ms=10000)

            execution_time = time.time() - start_time

            error = BasicTimingParser.detect_error(result.output)
            if error:
                return TimingResult(command=command, data={}, cached=False, execution_time=execution_time, error=error)

            parsed_data = self._parse_command_output(command, result.output)

            timing_result = TimingResult(command=command, data=parsed_data, cached=False, execution_time=execution_time)

            if use_cache:
                self._cache[cache_key] = timing_result
                logger.debug(f"Cached result for command: {command}")

            return timing_result

        except Exception as e:
            logger.exception(f"Error executing STA command: {e}")
            return TimingResult(command=command, data={}, cached=False, execution_time=0.0, error=str(e))

    async def get_summary(self) -> TimingSummary:
        """Get quick timing summary (WNS, TNS, path counts)"""
        if not self.design_name:
            return TimingSummary(design_name="No design loaded", wns=None, tns=None)

        summary = TimingSummary(design_name=self.design_name)

        try:
            wns_result = await self.execute_sta_command("report_wns")
            if not wns_result.error and "value" in wns_result.data:
                summary.wns = wns_result.data["value"]

            tns_result = await self.execute_sta_command("report_tns")
            if not tns_result.error and "value" in tns_result.data:
                summary.tns = tns_result.data["value"]

        except Exception as e:
            logger.exception(f"Error generating summary: {e}")

        return summary

    def clear_cache(self) -> None:
        """Clear all cached results"""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared cache ({cache_size} entries)")

    def _generate_cache_key(self, command: str) -> str:
        """Generate cache key for command"""
        return hashlib.md5(command.encode()).hexdigest()

    def _parse_command_output(self, command: str, output: str) -> dict[str, Any]:
        """Parse command output based on command type"""
        cmd_lower = command.lower()

        if "report_wns" in cmd_lower or "report_tns" in cmd_lower:
            return BasicTimingParser.parse_wns_tns(output, command)

        elif "report_checks" in cmd_lower:
            paths = BasicTimingParser.parse_report_checks(output)
            return {"paths": [p.model_dump() for p in paths], "path_count": len(paths)}

        elif "get_fanin" in cmd_lower or "get_fanout" in cmd_lower:
            pins = BasicTimingParser.parse_fanin_fanout(output)
            return {"pins": pins, "pin_count": len(pins)}

        else:
            return {"raw_output": output}
