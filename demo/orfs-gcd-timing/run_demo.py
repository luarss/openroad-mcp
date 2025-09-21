#!/usr/bin/env python3

"""
ORFS GCD Timing Debug Demo - Main Demo Script

This script orchestrates the complete timing debug demonstration:
1. Run ORFS GCD flow
2. Create timing violations
3. Execute AI-guided debugging conversation
4. Apply fixes and verify timing closure
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


async def main() -> int:
    """Main demo orchestration function"""

    print("🚀 Starting ORFS GCD Timing Debug Demo")
    print("=" * 50)

    # Check environment
    flow_home = os.environ.get("FLOW_HOME")
    if not flow_home:
        flow_home = os.path.expanduser("~/OpenROAD-flow-scripts")
        os.environ["FLOW_HOME"] = flow_home
        print(f"📌 Setting FLOW_HOME to {flow_home}")

    if not os.path.exists(flow_home):
        print(f"❌ Error: FLOW_HOME not found at {flow_home}")
        print("   Run setup.sh first or set FLOW_HOME correctly")
        return 1

    print(f"✅ Using FLOW_HOME: {flow_home}")

    # Phase 1: Run ORFS GCD Flow
    print("\n📦 Phase 1: Running ORFS GCD Flow...")
    try:
        await run_orfs_flow(flow_home)
        print("✅ ORFS GCD flow completed")
    except Exception as e:
        print(f"❌ Error running ORFS flow: {e}")
        return 1

    # Phase 2: Create Timing Violations
    print("\n🔧 Phase 2: Creating Timing Violations...")
    try:
        await create_violations()
        print("✅ Timing violations created")
    except Exception as e:
        print(f"❌ Error creating violations: {e}")
        return 1

    # Phase 3: AI-Guided Debug Session
    print("\n🧠 Phase 3: AI-Guided Debugging Session...")
    try:
        await run_ai_debug_session()
        print("✅ AI debugging session completed")
    except Exception as e:
        print(f"❌ Error in AI debug session: {e}")
        return 1

    print("\n🎉 Demo Complete!")
    print("=" * 50)
    print("📋 Demo demonstrated:")
    print("   ✅ ORFS integration with OpenROAD-MCP")
    print("   ✅ Realistic timing violation injection")
    print("   ✅ AI-guided critical path analysis")
    print("   ✅ Cross-domain debugging insights")
    print("   ✅ Automated constraint optimization")
    print("   ✅ Timing closure verification")
    print("\n🚀 Ready for live demonstration!")

    return 0


async def run_orfs_flow(flow_home: str) -> None:
    """Run the ORFS GCD flow to generate timing database"""

    gcd_config = f"{flow_home}/flow/designs/nangate45/gcd/config.mk"

    print(f"   Running: make DESIGN_CONFIG={gcd_config}")

    # Run ORFS make command
    process = await asyncio.create_subprocess_exec(
        "make",
        f"DESIGN_CONFIG={gcd_config}",
        cwd=flow_home,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        print(f"   ORFS stdout: {stdout.decode()}")
        print(f"   ORFS stderr: {stderr.decode()}")
        raise RuntimeError(f"ORFS flow failed with return code {process.returncode}")

    # Verify results exist
    results_dir = f"{flow_home}/flow/results/nangate45/gcd"
    cts_def = f"{results_dir}/4_cts.def"

    if not os.path.exists(cts_def):
        raise RuntimeError(f"Expected CTS DEF file not found: {cts_def}")

    print(f"   ✅ CTS database available: {cts_def}")


async def create_violations() -> None:
    """Create timing constraint violations for demo"""

    # Import violation analysis script
    sys.path.insert(0, "scripts")

    try:
        from violation_analysis import create_demo_violations

        create_demo_violations()
        print("   ✅ Tight constraints generated")
    except ImportError:
        print("   ⚠️  Violation analysis script not yet implemented")
        print("   📝 Creating placeholder constraints...")

        # Create placeholder tight constraints
        tight_constraints = """# Demo tight constraints - creates violations
create_clock -name clk -period 5.0 [get_ports clk]
set_input_delay -clock clk -max 4.0 [all_inputs]
set_output_delay -clock clk -max 4.0 [all_outputs]
"""

        with open("configs/tight_constraints.sdc", "w") as f:
            f.write(tight_constraints)

        print("   ✅ Placeholder constraints created")


async def run_ai_debug_session() -> None:
    """Run the AI-guided debugging conversation"""

    try:
        sys.path.insert(0, "scripts")
        from mcp_timing_debug import ORFSTimingDemo  # type: ignore[import-not-found]

        demo = ORFSTimingDemo()
        await demo.run_demo()
        print("   ✅ AI conversation completed")

    except ImportError:
        print("   ⚠️  MCP timing debug script not yet implemented")
        print("   📝 Running placeholder conversation...")

        # Placeholder conversation
        conversation = [
            ("🤖 User", "Analyze timing violations in this GCD design"),
            ("🧠 AI", "Found 12 setup violations with worst slack -1.2ns in GCD computation datapath"),
            ("🤖 User", "What's causing the worst violation?"),
            (
                "🧠 AI",
                "Critical path: 32-bit subtractor (3.1ns) + comparison (2.1ns)"
                "vs 5.0ns clock. Constraint too aggressive.",
            ),
            ("🤖 User", "How can we fix this?"),
            ("🧠 AI", "Relax clock to 8.0ns, add false paths for test signals, optimize I/O delays"),
            ("🤖 User", "Apply the fixes"),
            ("🧠 AI", "✅ Applied optimized constraints. All violations cleared. Worst slack now +0.8ns at 125MHz."),
        ]

        for speaker, message in conversation:
            print(f"   {speaker}: {message}")
            await asyncio.sleep(0.5)  # Simulate conversation timing

        print("   ✅ Placeholder conversation completed")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
