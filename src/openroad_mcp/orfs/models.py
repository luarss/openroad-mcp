"""Data models for ORFS flow execution."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ORFSPlatform(str, Enum):
    """Valid ORFS platforms."""

    ASAP7 = "asap7"
    GF180 = "gf180"
    IHP_SG13G2 = "ihp-sg13g2"
    NANGATE45 = "nangate45"
    SKY130HD = "sky130hd"
    SKY130HS = "sky130hs"
    SKY130IO = "sky130io"
    SKY130RAM = "sky130ram"


class ORFSDesign(str, Enum):
    """Valid ORFS designs."""

    AES = "aes"
    ARIANE133 = "ariane133"
    ARIANE136 = "ariane136"
    BLACK_PARROT = "black_parrot"
    BP_BE_TOP = "bp_be_top"
    BP_FE_TOP = "bp_fe_top"
    BP_MULTI_TOP = "bp_multi_top"
    BP_QUAD = "bp_quad"
    CHAMELEON = "chameleon"
    DYNAMIC_NODE = "dynamic_node"
    GCD = "gcd"
    IBEX = "ibex"
    JPEG = "jpeg"
    MEMPOOL_GROUP = "mempool_group"
    MICROWATT = "microwatt"
    RISCV32I = "riscv32i"
    SWERV = "swerv"
    SWERV_WRAPPER = "swerv_wrapper"
    TINY_ROCKET = "tinyRocket"


class FlowConfig(BaseModel):
    """Configuration for ORFS flow execution."""

    design_config: Path = Field(..., description="Path to design config.mk file")
    platform: ORFSPlatform = Field(default=ORFSPlatform.NANGATE45, description="Platform name")
    flow_root: Path = Field(default=Path("../OpenROAD-flow-scripts/flow"), description="ORFS flow directory")
    variables: dict[str, str] = Field(default_factory=dict, description="Additional make variables")
    timeout: float = Field(default=3600.0, description="Per-stage timeout in seconds")

    def to_make_args(self) -> list[str]:
        """Convert to make command arguments."""
        args = [f"DESIGN_CONFIG={self.design_config}"]

        if self.platform != ORFSPlatform.NANGATE45:
            args.append(f"PLATFORM={self.platform.value}")

        for key, value in self.variables.items():
            args.append(f"{key}={value}")

        return args


class StageResult(BaseModel):
    """Result of executing a single ORFS stage."""

    stage_name: str = Field(..., description="Name of the stage")
    success: bool = Field(..., description="Whether stage completed successfully")
    start_time: datetime = Field(default_factory=datetime.now, description="Stage start time")
    end_time: datetime | None = Field(default=None, description="Stage end time")
    return_code: int = Field(default=0, description="Process return code")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Extracted metrics")
    metrics_file: Path | None = Field(default=None, description="Path to metrics.json file")

    @property
    def duration(self) -> float | None:
        """Duration in seconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def failed(self) -> bool:
        """Whether stage failed."""
        return not self.success


class FlowResult(BaseModel):
    """Result of executing complete ORFS flow."""

    config: FlowConfig = Field(..., description="Flow configuration used")
    stages: list[StageResult] = Field(default_factory=list, description="Stage results")
    start_time: datetime = Field(default_factory=datetime.now, description="Flow start time")
    end_time: datetime | None = Field(default=None, description="Flow end time")

    def add_stage(self, stage: StageResult) -> None:
        """Add stage result to flow."""
        self.stages.append(stage)

    def all_stages_passed(self) -> bool:
        """Check if all stages completed successfully."""
        return all(stage.success for stage in self.stages)

    def get_failed_stages(self) -> list[StageResult]:
        """Get list of failed stages."""
        return [stage for stage in self.stages if stage.failed]

    def get_stage(self, name: str) -> StageResult | None:
        """Get stage result by name."""
        for stage in self.stages:
            if stage.stage_name == name:
                return stage
        return None

    def get_summary_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics across all stages."""
        summary: dict[str, Any] = {
            "total_stages": len(self.stages),
            "successful_stages": len([s for s in self.stages if s.success]),
            "failed_stages": len([s for s in self.stages if s.failed]),
            "total_duration": self.duration,
            "stage_metrics": {},
        }

        for stage in self.stages:
            if stage.metrics:
                summary["stage_metrics"][stage.stage_name] = stage.metrics

        return summary

    @property
    def duration(self) -> float | None:
        """Total duration in seconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "config": self.config.model_dump(),
            "stages": [stage.model_dump() for stage in self.stages],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": self.duration,
            "success": self.all_stages_passed(),
            "summary": self.get_summary_metrics(),
        }


class ORFSMetrics(BaseModel):
    """Standardized ORFS metrics structure."""

    stage: str = Field(..., description="Flow stage name")
    timestamp: datetime = Field(default_factory=datetime.now, description="Collection timestamp")

    # Timing metrics
    timing: dict[str, Any] = Field(default_factory=dict, description="Timing analysis results")

    # Power metrics
    power: dict[str, Any] = Field(default_factory=dict, description="Power analysis results")

    # Design metrics
    design: dict[str, Any] = Field(default_factory=dict, description="Design statistics")

    # Violations
    violations: dict[str, Any] = Field(default_factory=dict, description="Design rule violations")

    # Custom metrics
    custom: dict[str, Any] = Field(default_factory=dict, description="Custom/platform-specific metrics")

    @classmethod
    def from_raw_metrics(cls, stage: str, raw: dict[str, Any]) -> "ORFSMetrics":
        """Create from raw metrics.json data."""

        # Map file names to flow stage prefixes used in JSON
        stage_prefix_map = {
            "6_report": "finish",
            "6_1_fill": "finish",
            "5_3_fillcell": "route",
            "5_2_route": "route",
            "5_1_grt": "route",
            "4_1_cts": "cts",
            "3_5_place_dp": "place",
            "3_4_place_resized": "place",
            "3_3_place_gp": "place",
            "3_2_place_iop": "place",
            "3_1_place_gp_skip_io": "place",
            "2_4_floorplan_pdn": "floorplan",
            "2_3_floorplan_tapcell": "floorplan",
            "2_2_floorplan_macro": "floorplan",
            "2_1_floorplan": "floorplan",
            "1_2_yosys": "synth",
        }

        # Get the appropriate prefix for this stage
        flow_stage = stage_prefix_map.get(stage, stage)
        prefix = f"{flow_stage}__" if flow_stage else ""
        timing = {
            "wns": raw.get(f"{prefix}timing__setup__ws", raw.get("timing__setup__ws", 0)),
            "tns": raw.get(f"{prefix}timing__setup__tns", raw.get("timing__setup__tns", 0)),
            "hold_wns": raw.get(f"{prefix}timing__hold__ws", raw.get("timing__hold__ws", 0)),
            "hold_tns": raw.get(f"{prefix}timing__hold__tns", raw.get("timing__hold__tns", 0)),
            "clock_skew": raw.get(f"{prefix}clock__skew__setup", raw.get("timing__clk__skew", 0)),
            "clock_period": raw.get(f"{prefix}timing__clk__period", raw.get("timing__clk__period", 0)),
        }

        power = {
            "total": raw.get(f"{prefix}power__total", raw.get("power__total", 0)),
            "switching": raw.get(f"{prefix}power__switching__total", raw.get("power__switching", 0)),
            "internal": raw.get(f"{prefix}power__internal__total", raw.get("power__internal", 0)),
            "leakage": raw.get(f"{prefix}power__leakage__total", raw.get("power__leakage", 0)),
        }

        design = {
            "area": raw.get(f"{prefix}design__instance__area", raw.get("design__area", 0)),
            "core_area": raw.get(f"{prefix}design__core__area", raw.get("design__core_area", 0)),
            "die_area": raw.get(f"{prefix}design__die__area", raw.get("design__die_area", 0)),
            "utilization": raw.get(f"{prefix}design__instance__utilization", raw.get("design__utilization", 0)),
            "instance_count": raw.get(f"{prefix}design__instance__count", raw.get("design__instance_count", 0)),
            "wire_length": raw.get(f"{prefix}route__wirelength", raw.get("route__wirelength", 0)),
            "via_count": raw.get(f"{prefix}route__vias", raw.get("route__vias", 0)),
        }

        violations = {
            "drc": raw.get(f"{prefix}drc__count", raw.get("drc__count", 0)),
            "antenna": raw.get(f"{prefix}antenna__count", raw.get("antenna__count", 0)),
            "setup": raw.get(f"{prefix}timing__drv__setup_violation_count", raw.get("timing__setup__vio", 0)),
            "hold": raw.get(f"{prefix}timing__hold__vio", raw.get("timing__hold__vio", 0)),
        }

        # Build known keys set for custom filtering
        known_keys = set()
        for category in [timing, power, design, violations]:
            for value in category.values():
                # Find original keys that produced this value
                for orig_key, orig_value in raw.items():
                    if orig_value == value and value != 0:  # Only count non-zero matches
                        known_keys.add(orig_key)

        custom = {k: v for k, v in raw.items() if k not in known_keys}

        return cls(stage=stage, timing=timing, power=power, design=design, violations=violations, custom=custom)
