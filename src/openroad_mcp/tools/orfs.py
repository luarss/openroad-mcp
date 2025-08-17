"""Simple ORFS tools for MCP server."""

import json
from pathlib import Path

from ..core.manager import OpenROADManager
from ..orfs.runner import ORFSRunner
from ..utils.logging import get_logger


class ORFSTool:
    """ORFS tool that wraps make commands."""

    def __init__(self, manager: OpenROADManager | None = None):
        self.manager = manager
        self.logger = get_logger("orfs_tool")
        self._runner = None

    def _get_runner(self, flow_root: str | None = None, design_config: str | None = None) -> ORFSRunner:
        """Get or create ORFS runner instance."""
        flow_path = Path(flow_root) if flow_root else None
        config_path = Path(design_config) if design_config else None

        # Create new runner each time to allow different configs
        return ORFSRunner(flow_root=flow_path, design_config=config_path)

    async def make_clean_all(
        self, design_config: str, platform: str = "nangate45", flow_root: str | None = None, timeout: float = 300.0
    ) -> str:
        """Execute 'make clean_all' to clean previous build artifacts."""
        try:
            runner = self._get_runner(flow_root, design_config)

            # Validate setup first
            validation = runner.validate_setup()
            if not validation["valid"]:
                return json.dumps(
                    {"success": False, "error": "Invalid ORFS setup", "issues": validation["issues"]}, indent=2
                )

            # Run clean_all
            result = await runner.make_clean_all(design_config=design_config, platform=platform, timeout=timeout)

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.error(f"make clean_all failed: {e}")
            return json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__}, indent=2)

    async def make_flow(
        self,
        design_config: str,
        platform: str = "nangate45",
        flow_root: str | None = None,
        variables: dict[str, str] | None = None,
        timeout: float = 3600.0,
    ) -> str:
        """Execute 'make' to run the complete ORFS flow."""
        try:
            runner = self._get_runner(flow_root, design_config)

            # Validate setup first
            validation = runner.validate_setup()
            if not validation["valid"]:
                return json.dumps(
                    {"success": False, "error": "Invalid ORFS setup", "issues": validation["issues"]}, indent=2
                )

            # Run full flow
            result = await runner.make(
                design_config=design_config, platform=platform, variables=variables, timeout=timeout
            )

            return json.dumps(result, indent=2)

        except Exception as e:
            self.logger.error(f"make flow failed: {e}")
            return json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__}, indent=2)

    async def validate_orfs_setup(self, design_config: str, flow_root: str | None = None) -> str:
        """Validate ORFS setup and configuration."""
        try:
            runner = self._get_runner(flow_root, design_config)
            validation = runner.validate_setup()

            return json.dumps(validation, indent=2)

        except Exception as e:
            self.logger.error(f"ORFS validation failed: {e}")
            return json.dumps({"valid": False, "error": str(e), "error_type": type(e).__name__}, indent=2)

    async def get_final_metrics(
        self, design_config: str, flow_root: str | None = None, platform: str = "nangate45"
    ) -> str:
        """Get final metrics from the last completed ORFS flow stage."""
        try:
            runner = self._get_runner(flow_root, design_config)

            # Get the final metrics from the runner
            metrics_result = runner.get_final_metrics(platform=platform)

            return json.dumps(metrics_result, indent=2)

        except Exception as e:
            self.logger.error(f"Get final metrics failed: {e}")
            return json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__}, indent=2)
