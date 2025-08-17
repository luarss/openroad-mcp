"""Simple ORFS runner that wraps make commands."""

import asyncio
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger


class ORFSRunner:
    """Wrapper around ORFS make commands."""

    def __init__(self, flow_root: Path | None = None, design_config: Path | None = None):
        self.flow_root = flow_root or Path("../OpenROAD-flow-scripts/flow")
        self.design_config = design_config
        self.logger = get_logger("simple_orfs_runner")

    async def make_clean_all(
        self, design_config: str | None = None, platform: str = "nangate45", timeout: float = 300.0
    ) -> dict[str, Any]:
        """Execute 'make clean_all' command."""
        return await self._run_make_command(
            "clean_all", design_config=design_config, platform=platform, timeout=timeout
        )

    async def make(
        self,
        design_config: str | None = None,
        platform: str = "nangate45",
        variables: dict[str, str] | None = None,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        """Execute 'make' command (full flow)."""
        return await self._run_make_command(
            "",  # Empty target runs default (full flow)
            design_config=design_config,
            platform=platform,
            variables=variables,
            timeout=timeout,
        )

    async def _run_make_command(
        self,
        target: str,
        design_config: str | None = None,
        platform: str = "nangate45",
        variables: dict[str, str] | None = None,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        """Run make command with given parameters."""

        # Build command
        cmd = ["make"]
        if target:
            cmd.append(target)

        # Add design config
        if design_config:
            cmd.append(f"DESIGN_CONFIG={design_config}")
        elif self.design_config:
            cmd.append(f"DESIGN_CONFIG={self.design_config}")

        # Add platform if not default
        if platform != "nangate45":
            cmd.append(f"PLATFORM={platform}")

        # Add any additional variables
        if variables:
            for key, value in variables.items():
                cmd.append(f"{key}={value}")

        self.logger.info(f"Executing: {' '.join(cmd)}")

        try:
            # Run command
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=self.flow_root
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout}s",
                    "command": " ".join(cmd),
                    "return_code": -1,
                }

            stdout_str = stdout.decode("utf-8", errors="ignore")
            stderr_str = stderr.decode("utf-8", errors="ignore")

            result: dict[str, Any] = {
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "command": " ".join(cmd),
                "stdout": stdout_str,
                "stderr": stderr_str,
            }

            if process.returncode == 0:
                self.logger.info("Command completed successfully")
                # Try to collect metrics if this was a full make
                if not target:  # Full flow
                    result["metrics"] = await self._collect_metrics(design_config, platform)
            else:
                self.logger.error(f"Command failed with return code {process.returncode}")

            return result

        except Exception as e:
            self.logger.error(f"Error executing make command: {e}")
            return {"success": False, "error": str(e), "command": " ".join(cmd), "return_code": -1}

    async def _collect_metrics(self, design_config: str | None, platform: str) -> dict[str, Any]:
        """Collect metrics from completed flow."""
        try:
            from .metrics import MetricsCollector

            collector = MetricsCollector()

            # Extract design name - try config first, then fallback to default
            design_name = "unknown"
            if design_config:
                config_path = Path(design_config)
                design_name = collector.extract_design_name(config_path)

            # If still unknown, scan logs directory for existing designs
            if design_name == "unknown":
                logs_dir = self.flow_root / "logs" / platform
                if logs_dir.exists():
                    for design_dir in logs_dir.iterdir():
                        if design_dir.is_dir() and not design_dir.name.startswith("."):
                            # Check if this design has any metrics files (try multiple stages)
                            found_files = False
                            for stage in collector.get_valid_stages():
                                test_files = collector.find_all_metrics_files(
                                    self.flow_root, stage, platform, design_dir.name
                                )
                                if test_files:
                                    found_files = True
                                    break
                            if found_files:
                                design_name = design_dir.name
                                break

            # Look for metrics files from different stages
            stages = collector.get_valid_stages()
            collected_metrics = {}

            for stage in stages:
                # Get all metrics files for this stage (may have multiple substages)
                metrics_files = collector.find_all_metrics_files(self.flow_root, stage, platform, design_name)

                if metrics_files:
                    stage_metrics = {}
                    for metrics_file in metrics_files:
                        substage_name = metrics_file.stem  # e.g., "3_1_place_gp_skip_io"
                        metrics = collector.parse_metrics_json(metrics_file, substage_name)
                        if metrics:
                            stage_metrics[substage_name] = metrics.model_dump(mode="json")

                    if stage_metrics:
                        collected_metrics[stage] = stage_metrics

            return {
                "design_name": design_name,
                "platform": platform,
                "stages": collected_metrics,
                "total_stages": len(collected_metrics),
            }

        except Exception as e:
            self.logger.warning(f"Failed to collect metrics: {e}")
            return {"error": str(e)}

    def validate_setup(self) -> dict[str, Any]:
        """Validate ORFS setup."""
        issues = []

        # Check flow root exists
        if not self.flow_root.exists():
            issues.append(f"Flow root not found: {self.flow_root}")

        # Check Makefile exists
        makefile = self.flow_root / "Makefile"
        if not makefile.exists():
            issues.append(f"Makefile not found: {makefile}")

        # Check design config if provided
        if self.design_config and not self.design_config.exists():
            issues.append(f"Design config not found: {self.design_config}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "flow_root": str(self.flow_root),
            "design_config": str(self.design_config) if self.design_config else None,
        }

    def get_final_metrics(self, platform: str = "nangate45") -> dict[str, Any]:
        """Get final metrics from the most recent completed ORFS flow."""
        try:
            from .metrics import MetricsCollector

            collector = MetricsCollector()

            # Extract design name - try config first, then fallback to default
            design_name = "unknown"
            if self.design_config:
                design_name = collector.extract_design_name(self.design_config)

            # If still unknown, scan logs directory for existing designs
            if design_name == "unknown":
                logs_dir = self.flow_root / "logs" / platform
                if logs_dir.exists():
                    for design_dir in logs_dir.iterdir():
                        if design_dir.is_dir() and not design_dir.name.startswith("."):
                            # Check if this design has any metrics files (try multiple stages)
                            found_files = False
                            for stage in collector.get_valid_stages():
                                test_files = collector.find_all_metrics_files(
                                    self.flow_root, stage, platform, design_dir.name
                                )
                                if test_files:
                                    found_files = True
                                    break
                            if found_files:
                                design_name = design_dir.name
                                break

            # Look for the latest metrics from all stages
            stages = collector.get_valid_stages()
            stage_order = ["synth", "floorplan", "place", "cts", "route", "finish"]

            # Find the most advanced stage with metrics
            final_stage = None
            for stage in reversed(stage_order):
                metrics_files = collector.find_all_metrics_files(self.flow_root, stage, platform, design_name)
                if metrics_files:
                    final_stage = stage
                    break

            if not final_stage:
                return {
                    "success": False,
                    "error": "No metrics files found",
                    "design_name": design_name,
                    "platform": platform,
                }

            # Collect final stage metrics
            metrics_files = collector.find_all_metrics_files(self.flow_root, final_stage, platform, design_name)
            final_stage_metrics = {}

            for metrics_file in metrics_files:
                substage_name = metrics_file.stem
                metrics = collector.parse_metrics_json(metrics_file, substage_name)
                if metrics:
                    final_stage_metrics[substage_name] = metrics.model_dump(mode="json")

            # Also collect summary across all available stages
            all_stages_metrics = []
            for stage in stages:
                stage_files = collector.find_all_metrics_files(self.flow_root, stage, platform, design_name)
                for stage_file in stage_files:
                    substage_name = stage_file.stem
                    metrics = collector.parse_metrics_json(stage_file, substage_name)
                    if metrics:
                        all_stages_metrics.append(metrics)

            # Use aggregated metrics if we have multiple stages
            aggregated = collector.aggregate_metrics(all_stages_metrics) if all_stages_metrics else {}

            return {
                "success": True,
                "design_name": design_name,
                "platform": platform,
                "final_stage": final_stage,
                "final_stage_metrics": final_stage_metrics,
                "aggregated_metrics": aggregated,
                "total_metrics_files": len(all_stages_metrics),
            }

        except Exception as e:
            self.logger.error(f"Failed to get final metrics: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }
