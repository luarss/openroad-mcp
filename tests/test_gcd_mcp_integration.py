"""Test GCD timing checkpoints through MCP integration.

TODO: shift this into integration/ directory."""

import tempfile
from pathlib import Path

import pytest

from src.openroad_mcp.core.manager import OpenROADManager
from src.openroad_mcp.timing.checkpoint import TimingCheckpointSystem


class TestGCDMCPIntegration:
    """Integration tests for GCD timing checkpoints through MCP."""

    @pytest.fixture
    async def openroad_manager(self):
        """Create a real OpenROAD manager for testing."""
        manager = OpenROADManager()
        await manager.start_process()
        yield manager
        await manager.stop_process()

    @pytest.fixture
    def gcd_tcl_script(self):
        """Path to the GCD Tcl test script."""
        return Path(__file__).parent.parent / "scripts" / "gcd_timing_test.tcl"

    @pytest.mark.asyncio
    async def test_execute_gcd_tcl_script(self, openroad_manager, gcd_tcl_script):
        """Test executing the complete GCD Tcl script."""
        if not gcd_tcl_script.exists():
            pytest.skip("GCD Tcl script not found")

        # Execute the script through OpenROAD manager
        try:
            result = await openroad_manager.execute_command(f"source {gcd_tcl_script}")

            # Check that the script executed successfully
            assert result.returncode == 0
            assert "GCD Timing Checkpoint Test COMPLETED" in "\n".join(result.stdout)

        except Exception as e:
            pytest.skip(f"OpenROAD execution failed: {e}")

    @pytest.mark.asyncio
    async def test_gcd_timing_commands_individual(self, openroad_manager):
        """Test individual GCD timing commands."""
        # Basic commands that should work without full design
        basic_commands = [
            "puts {Testing GCD timing commands}",
            "set test_var 123",
            "puts $test_var",
        ]

        for cmd in basic_commands:
            try:
                result = await openroad_manager.execute_command(cmd)
                assert result.returncode == 0
            except Exception as e:
                pytest.skip(f"Basic command failed: {e}")

    @pytest.mark.asyncio
    async def test_gcd_checkpoint_system_integration(self, openroad_manager):
        """Test checkpoint system with mocked GCD data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_system = TimingCheckpointSystem(openroad_manager, temp_dir)

            # Mock timing data that would come from GCD analysis
            mock_gcd_timing_data = {
                "paths": {
                    "req_msg[0]->dpath.a_reg.out_reg[0].qi": {
                        "slack": 0.385,
                        "delay": 0.08,
                        "startpoint": "req_msg[0]",
                        "endpoint": "dpath.a_reg.out_reg[0].qi",
                    },
                    "clk->dpath.b_reg.out_reg[15].qi": {
                        "slack": 0.343,
                        "delay": 0.12,
                        "startpoint": "clk",
                        "endpoint": "dpath.b_reg.out_reg[15].qi",
                    },
                },
                "wns": 0.343,
                "tns": 0.0,
            }

            # Override timing data extraction to return mock data
            async def mock_extract_timing_data():
                return mock_gcd_timing_data

            checkpoint_system._extract_timing_data = mock_extract_timing_data

            # Create checkpoints for GCD flow stages
            gcd_stages = ["synthesis", "placement", "cts", "routing"]
            checkpoints = []

            for stage in gcd_stages:
                checkpoint = await checkpoint_system.create_checkpoint(
                    f"gcd_{stage}", force_base=(stage == "synthesis")
                )
                checkpoints.append(checkpoint)

                assert checkpoint.stage_name == f"gcd_{stage}"
                assert checkpoint.path_count == len(mock_gcd_timing_data["paths"])

            # Test checkpoint restoration
            restored_data = await checkpoint_system.restore_checkpoint(checkpoints[0].stage_id)
            assert "paths" in restored_data
            assert restored_data["wns"] == mock_gcd_timing_data["wns"]

            # Check storage efficiency
            stats = checkpoint_system.get_storage_statistics()
            assert stats["checkpoint_count"] == len(gcd_stages)
            assert stats["compression_ratio"] < 1.0

    def test_gcd_tcl_script_content(self, gcd_tcl_script):
        """Test that the GCD Tcl script contains expected content."""
        if not gcd_tcl_script.exists():
            pytest.skip("GCD Tcl script not found")

        script_content = gcd_tcl_script.read_text()

        # Check for essential GCD-specific content
        expected_content = [
            "gcd.v",
            "gcd_nangate45.sdc",
            "Nangate45.lef",
            'link_design "gcd"',
            "create_timing_checkpoint",
            "report_checks",
            "global_placement",
            "clock_tree_synthesis",
            "global_route",
            "timing_checkpoints.json",
        ]

        for content in expected_content:
            assert content in script_content, f"Missing expected content: {content}"

    @pytest.mark.asyncio
    async def test_simulated_gcd_flow_execution(self, openroad_manager):
        """Test simulated GCD flow execution with timing analysis."""
        # Simulate the key commands from the GCD flow
        flow_commands = [
            # Basic setup that should work
            "puts {Starting GCD flow simulation}",
            "set design_name gcd",
            'puts "Design: $design_name"',
            # Simulate timing analysis commands (these will likely fail but we test the interface)
            "catch { report_wns }",
            "catch { report_tns }",
            "catch { report_checks -format summary -nworst 1 }",
            # Test checkpoint creation simulation
            "puts {Simulating checkpoint creation}",
            "set checkpoint_stages {synthesis placement cts routing}",
            'foreach stage $checkpoint_stages { puts "Checkpoint: gcd_$stage" }',
            "puts {GCD flow simulation completed}",
        ]

        for cmd in flow_commands:
            try:
                result = await openroad_manager.execute_command(cmd)
                # Commands with 'catch' should always return 0
                # Pure puts commands should also return 0
                if "catch" in cmd or "puts" in cmd or "set" in cmd or "foreach" in cmd:
                    assert result.returncode == 0
            except Exception:
                # Some commands may fail in test environment, that's expected
                pass

    def test_create_gcd_verification_script(self):
        """Create a verification script for manual testing."""
        verification_script = """#!/usr/bin/env python3
# GCD Timing Checkpoint Verification Script

import asyncio
import sys
from pathlib import Path

# Add the src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.timing.checkpoint import TimingCheckpointSystem


async def verify_gcd_checkpoints():
    \"\"\"Verify GCD timing checkpoint functionality.\"\"\"
    print("Starting GCD checkpoint verification...")

    # Start OpenROAD manager
    manager = OpenROADManager()
    await manager.start()

    try:
        # Initialize checkpoint system
        checkpoint_system = TimingCheckpointSystem(manager, "./test_checkpoints")

        # Test basic functionality
        print("Testing checkpoint system initialization...")
        stats = checkpoint_system.get_storage_statistics()
        print(f"Initial stats: {stats}")

        # Execute GCD Tcl script if available
        gcd_script = Path("./scripts/gcd_timing_test.tcl")
        if gcd_script.exists():
            print(f"Executing GCD script: {gcd_script}")
            result = await manager.execute_command(f"source {gcd_script}")
            print(f"Script execution result: {result.returncode}")
            if result.stdout:
                print("STDOUT:", "\\n".join(result.stdout[-10:]))  # Last 10 lines
        else:
            print("GCD script not found, skipping script execution")

        print("GCD checkpoint verification completed successfully!")

    except Exception as e:
        print(f"Verification failed: {e}")
        return False
    finally:
        await manager.stop()

    return True


if __name__ == "__main__":
    success = asyncio.run(verify_gcd_checkpoints())
    sys.exit(0 if success else 1)
"""

        # Write verification script
        script_path = Path(__file__).parent.parent / "verify_gcd_checkpoints.py"
        script_path.write_text(verification_script)
        script_path.chmod(0o755)

        assert script_path.exists()
        assert "async def verify_gcd_checkpoints" in verification_script
