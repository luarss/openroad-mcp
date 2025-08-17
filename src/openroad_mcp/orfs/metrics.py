"""ORFS metrics collection and parsing utilities."""

import json
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger
from .models import ORFSMetrics


class MetricsCollector:
    """Collects and parses ORFS metrics from JSON files."""

    # Map stage names to actual ORFS JSON file names
    STAGE_TO_FILE_MAP = {
        "synth": ["1_2_yosys"],
        "floorplan": ["2_1_floorplan", "2_2_floorplan_macro", "2_3_floorplan_tapcell", "2_4_floorplan_pdn"],
        "place": ["3_1_place_gp_skip_io", "3_2_place_iop", "3_3_place_gp", "3_4_place_resized", "3_5_place_dp"],
        "cts": ["4_1_cts"],
        "route": ["5_1_grt", "5_2_route", "5_3_fillcell"],
        "finish": ["6_1_fill", "6_report"],
    }

    def __init__(self) -> None:
        self.logger = get_logger("metrics_collector")

    def parse_metrics_json(self, json_path: Path, stage_name: str) -> ORFSMetrics | None:
        """Parse stage metrics.json file."""
        if not json_path.exists():
            self.logger.warning(f"Metrics file not found: {json_path}")
            return None

        try:
            with open(json_path) as f:
                raw_metrics = json.load(f)

            self.logger.debug(f"Loaded {len(raw_metrics)} metrics from {json_path}")
            return ORFSMetrics.from_raw_metrics(stage_name, raw_metrics)

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in metrics file {json_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing metrics from {json_path}: {e}")
            return None

    def _get_metrics_path(self, flow_dir: Path, file_name: str, platform: str, design: str) -> Path | None:
        """Get the primary metrics file path (first possible location only).
        TODO: Make this also configurable by setting `design_variant` variable.
        """
        path = flow_dir / "logs" / platform / design / "base" / f"{file_name}.json"
        return path if path.exists() else None

    def find_metrics_file(
        self, flow_dir: Path, stage_name: str, platform: str = "nangate45", design: str = "gcd"
    ) -> Path | None:
        """Find metrics.json file for given stage."""
        possible_files = self.STAGE_TO_FILE_MAP.get(stage_name, [stage_name])

        for file_name in possible_files:
            path = self._get_metrics_path(flow_dir, file_name, platform, design)
            if path:
                self.logger.debug(f"Found metrics file: {path}")
                return path

        self.logger.warning(f"No metrics file found for stage {stage_name}")
        return None

    def find_all_metrics_files(
        self, flow_dir: Path, stage_name: str, platform: str = "nangate45", design: str = "gcd"
    ) -> list[Path]:
        """Find all metrics.json files for given stage."""
        possible_files = self.STAGE_TO_FILE_MAP.get(stage_name, [stage_name])
        found_files = []

        for file_name in possible_files:
            path = self._get_metrics_path(flow_dir, file_name, platform, design)
            if path:
                found_files.append(path)

        return found_files

    @classmethod
    def get_valid_stages(cls) -> list[str]:
        """Get list of valid ORFS stage names."""
        return list(cls.STAGE_TO_FILE_MAP.keys())

    @classmethod
    def get_stage_substages(cls, stage: str) -> list[str]:
        """Get list of substages for a given stage."""
        return cls.STAGE_TO_FILE_MAP.get(stage, [])

    def extract_design_name(self, config_path: Path) -> str:
        """Extract design name from config.mk file."""
        try:
            with open(config_path) as f:
                content = f.read()

            # Look for DESIGN_NAME variable
            for line in content.split("\n"):
                if line.strip().startswith("DESIGN_NAME"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip("\"'")

            # Fallback: use parent directory name
            return config_path.parent.name

        except Exception as e:
            self.logger.warning(f"Could not extract design name from {config_path}: {e}")
            return "unknown"

    def validate_metrics(self, metrics: ORFSMetrics) -> bool:
        """Validate metrics data for completeness."""
        required_fields = ["timing", "design"]

        for field in required_fields:
            if not getattr(metrics, field):
                self.logger.warning(f"Missing required metrics field: {field}")
                return False

        # Check for reasonable values
        if metrics.design.get("area", 0) <= 0:
            self.logger.warning("Design area is zero or negative")

        if metrics.design.get("instance_count", 0) <= 0:
            self.logger.warning("Instance count is zero or negative")

        return True

    def aggregate_metrics(self, metrics_list: list[ORFSMetrics]) -> dict[str, Any]:
        """Aggregate metrics across multiple stages."""
        if not metrics_list:
            return {}

        # Build progressions
        timing_progression = [
            {
                "stage": m.stage,
                "wns": m.timing.get("wns", 0),
                "tns": m.timing.get("tns", 0),
                "timestamp": m.timestamp.isoformat(),
            }
            for m in metrics_list
        ]

        area_progression = [
            {
                "stage": m.stage,
                "area": m.design.get("area", 0),
                "utilization": m.design.get("utilization", 0),
            }
            for m in metrics_list
        ]

        # Build violations summary
        violations_summary: dict[str, list[dict[str, Any]]] = {}
        for metrics in metrics_list:
            for vio_type, count in metrics.violations.items():
                violations_summary.setdefault(vio_type, []).append({"stage": metrics.stage, "count": count})

        # Final metrics from last stage
        final = metrics_list[-1]
        final_metrics = {
            "timing": final.timing,
            "power": final.power,
            "design": final.design,
            "violations": final.violations,
        }

        return {
            "stages": [m.stage for m in metrics_list],
            "timing_progression": timing_progression,
            "area_progression": area_progression,
            "violations_summary": violations_summary,
            "final_metrics": final_metrics,
        }
