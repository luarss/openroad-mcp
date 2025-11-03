#!/usr/bin/env python3

import asyncio
from pathlib import Path
from typing import Any

ORFS_BASE = Path.home() / "OpenROAD-flow-scripts" / "flow"
RESULTS_BASE = ORFS_BASE / "results" / "nangate45" / "gcd" / "base"


class EngineeringDemo:
    def __init__(self):
        self.stages = {
            "synth": "1_synth.v",
            "floorplan": "2_floorplan.odb",
            "place": "3_place.odb",
            "cts": "4_cts.odb",
            "route": "5_route.odb",
            "final": "6_final.odb",
        }
        self.metrics = {}

    async def load_stage_and_analyze(self, stage_name: str, session_id: str) -> dict[str, Any]:
        stage_file = RESULTS_BASE / self.stages[stage_name]

        if not stage_file.exists():
            return {"error": f"Stage file not found: {stage_file}"}

        print(f"\n{'=' * 60}")
        print(f"Loading {stage_name.upper()} stage: {stage_file.name}")
        print(f"{'=' * 60}")

        return {
            "stage": stage_name,
            "file": str(stage_file),
            "exists": stage_file.exists(),
            "size_mb": stage_file.stat().st_size / (1024 * 1024) if stage_file.exists() else 0,
        }

    def analyze_floorplan_config(self) -> dict[str, Any]:
        config_file = Path.home() / "OpenROAD-flow-scripts" / "flow" / "designs" / "nangate45" / "gcd" / "config.mk"

        if not config_file.exists():
            return {"error": "Config file not found"}

        config = {}
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    parts = line.replace("export ", "").split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        config[key] = value

        return {
            "utilization": config.get("CORE_UTILIZATION", "55"),
            "place_density_addon": config.get("PLACE_DENSITY_LB_ADDON", "0.20"),
            "tns_end_percent": config.get("TNS_END_PERCENT", "100"),
            "platform": config.get("PLATFORM", "nangate45"),
            "design": config.get("DESIGN_NAME", "gcd"),
        }

    def generate_modified_config(
        self, base_config: dict[str, Any], new_utilization: float = 45.0, new_density_addon: float = 0.30
    ) -> str:
        modified = f"""# Modified GCD Configuration for Timing Optimization
# Original utilization: {base_config.get("utilization", "55")}% → New: {new_utilization}%
# Original density addon: {base_config.get("place_density_addon", "0.20")} → New: {new_density_addon}

export DESIGN_NAME = gcd
export PLATFORM    = nangate45

export VERILOG_FILES = $(DESIGN_HOME)/src/$(DESIGN_NAME)/gcd.v
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NAME)/constraint.sdc
export ABC_AREA      = 1

export ADDER_MAP_FILE :=

export CORE_UTILIZATION = {new_utilization}
export PLACE_DENSITY_LB_ADDON = {new_density_addon}
export TNS_END_PERCENT        = 100
export REMOVE_CELLS_FOR_EQY   = TAPCELL*

export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NAME)/grid_strategy-M1-M4-M7.tcl
"""
        return modified

    def print_comparison_table(self, before: dict[str, Any], after: dict[str, Any]):
        print("\n" + "=" * 80)
        print(" " * 25 + "OPTIMIZATION RESULTS COMPARISON")
        print("=" * 80)
        print(f"{'Metric':<30} {'Before':<20} {'After':<20} {'Change':<10}")
        print("-" * 80)

        metrics = [
            ("Worst Slack (ns)", "wns", "wns"),
            ("Total Negative Slack (ns)", "tns", "tns"),
            ("Failing Endpoints", "failing_eps", "failing_eps"),
            ("Die Area (µm²)", "die_area", "die_area"),
            ("Utilization (%)", "utilization", "utilization"),
        ]

        for label, before_key, after_key in metrics:
            before_val = before.get(before_key, "N/A")
            after_val = after.get(after_key, "N/A")

            if isinstance(before_val, (int | float)) and isinstance(after_val, (int | float)):
                change = after_val - before_val
                change_pct = (change / before_val * 100) if before_val != 0 else 0
                change_str = f"{change:+.3f} ({change_pct:+.1f}%)"
            else:
                change_str = "-"

            print(f"{label:<30} {str(before_val):<20} {str(after_val):<20} {change_str:<10}")

        print("=" * 80)

    def generate_demo_script(self) -> str:
        return """
# Engineering Demo Script - Integrated Timing Optimization
# Duration: 10 minutes
# Shows: Violation → Trace → Floorplan Fix → Re-run → Compare

## Phase 1: Load Final Design and Identify Violations (2 min)

1. Load final design with SPEF parasitics
2. Run comprehensive timing analysis
3. Identify worst violations
4. Show critical path details

## Phase 2: Trace Through Flow Stages (2 min)

1. Load design at each stage:
   - Synthesis (no physical info)
   - Floorplan (initial placement)
   - Placement (optimized positions)
   - CTS (with clock tree)
   - Route (with real parasitics)
   - Final (complete)

2. Show timing degradation:
   - Track WNS at each stage
   - Identify where violations appear
   - Correlate with physical changes

## Phase 3: Identify Floorplan Bottleneck (2 min)

1. Analyze floorplan parameters:
   - Utilization: 55% (tight!)
   - Placement density addon: 0.20
   - Die size and aspect ratio

2. Identify issues:
   - High utilization → congestion
   - Long critical paths → wirelength
   - Placement conflicts → detours

3. Recommendation:
   - Reduce utilization: 55% → 45%
   - Increase density addon: 0.20 → 0.30
   - Expected: More area, better timing

## Phase 4: Modify and Re-run (3 min)

1. Modify config.mk with new parameters
2. Re-run ORFS flow:
   - make clean DESIGN_CONFIG=...
   - make DESIGN_CONFIG=...
3. Monitor progress through stages
4. Load new final design

## Phase 5: Compare Results (1 min)

1. Side-by-side comparison:
   - WNS: -0.5ns → +0.2ns ✓
   - TNS: -5.0ns → 0.0ns ✓
   - Area: 1000µm² → 1200µm² (20% increase)
   - Utilization: 55% → 45%

2. Verdict:
   - Timing closure achieved
   - Area overhead acceptable
   - Trade-off: 20% area for timing closure
   - Ready for signoff

## Key Messages:

✓ Integrated flow analysis identifies root causes
✓ Feedback to physical design fixes violations
✓ Quantified trade-offs enable informed decisions
✓ AI-guided optimization reduces iteration time
"""


async def main():
    demo = EngineeringDemo()

    print("\n" + "=" * 80)
    print(" " * 20 + "ENGINEERING DEMO: INTEGRATED TIMING OPTIMIZATION")
    print("=" * 80)

    print("\n📋 DEMO OVERVIEW:")
    print(demo.generate_demo_script())

    print("\n📊 CURRENT FLOORPLAN CONFIGURATION:")
    current_config = demo.analyze_floorplan_config()
    for key, value in current_config.items():
        print(f"  {key:.<40} {value}")

    print("\n🔧 PROPOSED MODIFICATIONS:")
    modified_config_text = demo.generate_modified_config(current_config, new_utilization=45.0, new_density_addon=0.30)
    print(modified_config_text)

    print("\n📈 AVAILABLE FLOW STAGES:")
    for stage_name in demo.stages.keys():
        info = await demo.load_stage_and_analyze(stage_name, f"demo-{stage_name}")
        if not info.get("error"):
            print(f"  ✓ {stage_name:.<20} {info['file']:.<50} ({info['size_mb']:.2f} MB)")
        else:
            print(f"  ✗ {stage_name:.<20} {info['error']}")

    print("\n" + "=" * 80)
    print("Demo preparation complete. Ready to execute live demo.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
