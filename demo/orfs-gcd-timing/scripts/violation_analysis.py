#!/usr/bin/env python3

"""
Timing Constraint Violation Analysis for ORFS GCD Demo

This script creates timing constraint variants that inject realistic
violations for the demo, and provides analysis utilities.
"""

import os
import re
from pathlib import Path


def create_demo_violations() -> None:
    """Create SDC constraint files for demo violations and fixes"""

    # Get FLOW_HOME environment variable
    flow_home = os.environ.get("FLOW_HOME", os.path.expanduser("~/OpenROAD-flow-scripts"))
    original_sdc = f"{flow_home}/flow/designs/nangate45/gcd/constraint.sdc"

    # Output paths
    configs_dir = Path(__file__).parent.parent / "configs"
    configs_dir.mkdir(exist_ok=True)

    tight_sdc = configs_dir / "tight_constraints.sdc"
    relaxed_sdc = configs_dir / "relaxed_constraints.sdc"

    print(f"📄 Reading original constraints from: {original_sdc}")

    # Read original constraints
    try:
        with open(original_sdc) as f:
            original_constraints = f.read()
    except FileNotFoundError:
        print(f"⚠️  Original constraint file not found: {original_sdc}")
        print("   Creating constraints from template...")
        original_constraints = create_default_constraints()

    # Create tight constraints (violations)
    tight_constraints = create_tight_constraints(original_constraints)
    with open(tight_sdc, "w") as f:
        f.write(tight_constraints)
    print(f"✅ Created tight constraints: {tight_sdc}")

    # Create relaxed constraints (fixes)
    relaxed_constraints = create_relaxed_constraints(original_constraints)
    with open(relaxed_sdc, "w") as f:
        f.write(relaxed_constraints)
    print(f"✅ Created relaxed constraints: {relaxed_sdc}")


def create_default_constraints() -> str:
    """Create default GCD constraints if original not found"""
    return """# Default GCD constraints
create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay -clock clk -max 2.0 [all_inputs]
set_output_delay -clock clk -max 2.0 [all_outputs]
set_load 0.1 [all_outputs]
"""


def create_tight_constraints(original: str) -> str:
    """Create over-constrained SDC that produces violations"""

    # Start with header
    constraints = """# ORFS GCD Demo - Tight Constraints (Creates Violations)
# This file contains over-aggressive timing constraints that will
# create realistic timing violations for demonstration purposes.

"""

    # Replace clock period variable with tight constraint
    modified = re.sub(r"set clk_period [\d.]+", "set clk_period 5.0", original)

    # Also handle direct clock creation
    modified = re.sub(
        r"create_clock\s+.*?-period\s+[\d.]+", "create_clock -name clk -period 5.0", modified, flags=re.IGNORECASE
    )

    # If no clock found, add one
    if "create_clock" not in modified and "clk_period" not in modified:
        modified = "create_clock -name clk -period 5.0 [get_ports clk]\n" + modified

    constraints += (
        modified
        + """

# Aggressive I/O constraints for demo violations
set_input_delay -clock clk -max 4.0 [all_inputs]
set_output_delay -clock clk -max 4.0 [all_outputs]

# Remove false paths that should exist (creates more violations)
# set_false_path -from [get_ports reset] (commented out for violations)
# set_false_path -from [get_ports test_en] (commented out for violations)

# Tight load requirements
set_load 0.05 [all_outputs]
"""
    )

    return constraints


def create_relaxed_constraints(original: str) -> str:
    """Create achievable SDC constraints that fix violations"""

    # Start with header
    constraints = """# ORFS GCD Demo - Relaxed Constraints (Fixes Violations)
# This file contains realistic timing constraints that achieve
# timing closure for the GCD design.

"""

    # Replace clock period variable with relaxed constraint
    modified = re.sub(r"set clk_period [\d.]+", "set clk_period 8.0", original)

    # Also handle direct clock creation
    modified = re.sub(
        r"create_clock\s+.*?-period\s+[\d.]+", "create_clock -name clk -period 8.0", modified, flags=re.IGNORECASE
    )

    # If no clock found, add one
    if "create_clock" not in modified and "clk_period" not in modified:
        modified = "create_clock -name clk -period 8.0 [get_ports clk]\n" + modified

    constraints += (
        modified
        + """

# Realistic I/O constraints
set_input_delay -clock clk -max 1.0 [all_inputs]
set_output_delay -clock clk -max 1.0 [all_outputs]

# Proper false path declarations
set_false_path -from [get_ports reset]
set_false_path -to [get_ports reset]

# False paths for test signals (if they exist)
set_false_path -from [get_ports test_en] -to [all_registers]
set_false_path -from [get_ports scan_en] -to [all_registers]

# Reasonable load requirements
set_load 0.1 [all_outputs]

# Clock uncertainty and transition time
set_clock_uncertainty 0.1 [get_clocks clk]
set_clock_transition 0.1 [get_clocks clk]
"""
    )

    return constraints


def analyze_constraints_difference() -> None:
    """Analyze the difference between tight and relaxed constraints"""

    configs_dir = Path(__file__).parent.parent / "configs"
    tight_file = configs_dir / "tight_constraints.sdc"
    relaxed_file = configs_dir / "relaxed_constraints.sdc"

    if not tight_file.exists() or not relaxed_file.exists():
        print("❌ Constraint files not found. Run create_demo_violations() first.")
        return

    print("📊 Constraint Analysis:")
    print("=" * 40)

    # Extract key timing parameters
    def extract_clock_period(file_path: Path) -> float | None:
        with open(file_path) as f:
            content = f.read()
        # Look for TCL variable definition
        match = re.search(r"set clk_period ([\d.]+)", content)
        if match:
            return float(match.group(1))
        # Look for direct create_clock with -period parameter
        match = re.search(r"create_clock.*?-period\s+([\d.]+)", content, re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
        # Try alternative format
        match = re.search(r"-period\s+([\d.]+)", content, re.IGNORECASE)
        return float(match.group(1)) if match else None

    def extract_io_delay(file_path: Path, direction: str) -> float | None:
        with open(file_path) as f:
            content = f.read()
        pattern = f"set_{direction}_delay.*?-max\\s+([\\d.]+)"
        match = re.search(pattern, content, re.IGNORECASE)
        return float(match.group(1)) if match else None

    tight_clock = extract_clock_period(tight_file)
    relaxed_clock = extract_clock_period(relaxed_file)

    tight_input = extract_io_delay(tight_file, "input")
    relaxed_input = extract_io_delay(relaxed_file, "input")

    print("Clock Period:")
    if tight_clock and relaxed_clock:
        print(f"  Tight: {tight_clock}ns -> {1000 / tight_clock:.0f}MHz")
        print(f"  Relaxed: {relaxed_clock}ns -> {1000 / relaxed_clock:.0f}MHz")
        print(f"  Improvement: {((relaxed_clock - tight_clock) / tight_clock * 100):.1f}% period increase")
    else:
        print(f"  Tight: {tight_clock}ns")
        print(f"  Relaxed: {relaxed_clock}ns")

    print("\nI/O Delays:")
    if tight_input and relaxed_input:
        print(f"  Tight: {tight_input}ns input delay")
        print(f"  Relaxed: {relaxed_input}ns input delay")
        print(f"  Improvement: {tight_input - relaxed_input}ns reduction")
    else:
        print(f"  Tight: {tight_input}ns")
        print(f"  Relaxed: {relaxed_input}ns")

    print("\nExpected Impact:")
    print("  🔴 Tight constraints should create 10-15 violations")
    print("  🟢 Relaxed constraints should achieve timing closure")
    if tight_clock and relaxed_clock:
        print(
            f"""
            📈 Demonstrates {((relaxed_clock - tight_clock) / tight_clock * 100):.0f}%
            performance impact of proper constraints
            """
        )
    else:
        print("  📈 Demonstrates timing closure through constraint optimization")


if __name__ == "__main__":
    print("🔧 Creating ORFS GCD Demo Constraint Variants")
    create_demo_violations()
    print("\n📊 Analyzing constraint differences...")
    analyze_constraints_difference()
    print("\n✅ Constraint generation complete!")
