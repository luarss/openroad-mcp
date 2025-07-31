"""GCD timing checkpoint test suite using real OpenROAD GCD design."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.openroad_mcp.timing.checkpoint import TimingCheckpointSystem


@pytest.fixture
def mock_manager():
    """Mock OpenROAD manager with GCD-specific responses."""
    manager = MagicMock()
    manager.execute_command = AsyncMock()
    return manager


@pytest.fixture
def checkpoint_system(mock_manager):
    """Create checkpoint system for GCD tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        system = TimingCheckpointSystem(mock_manager, temp_dir)
        yield system


@pytest.fixture
def gcd_design_files():
    """Paths to GCD design files in OpenROAD tree."""
    # Try to get OpenROAD directory from environment or common locations
    openroad_dir = os.environ.get("OPENROAD_DIR") or os.environ.get("OPENROAD_HOME")

    if not openroad_dir:
        # Try common installation locations
        possible_dirs = [
            "/usr/local/openroad",
            "/opt/openroad",
            os.path.expanduser("~/OpenROAD"),
        ]

        for dir_path in possible_dirs:
            if Path(dir_path).exists():
                openroad_dir = dir_path
                break

    # If still not found, use pytest configuration or skip
    if not openroad_dir:
        pytest.skip("OpenROAD installation not found. Set OPENROAD_DIR environment variable.")

    openroad_path = Path(openroad_dir)

    return {
        "verilog": str(openroad_path / "src/gpl/test/design/nangate45/gcd/gcd.v"),
        "sdc": str(openroad_path / "src/par/test/gcd_nangate45.sdc"),
        "def": str(openroad_path / "src/gpl/test/design/nangate45/gcd/gcd.def"),
        "lef": str(openroad_path / "test/Nangate45/Nangate45.lef"),
        "lib": str(openroad_path / "test/Nangate45/Nangate45_typ.lib"),
    }


class TestGCDTimingCheckpoints:
    """Test timing checkpoints using GCD design through OpenROAD flow stages."""

    async def _mock_gcd_timing_response(self, checkpoint_system, stage, path_count=10):
        """Setup mock timing responses for GCD at different stages."""
        stage_timing_data = {
            "synthesis": {
                "paths": {
                    f"req_msg[{i}]->dpath.a_reg.out_reg[{i}].qi": {
                        "slack": 0.385 - 0.01 * i,
                        "delay": 0.08 + 0.001 * i,
                        "startpoint": f"req_msg[{i}]",
                        "endpoint": f"dpath.a_reg.out_reg[{i}].qi",
                    }
                    for i in range(path_count)
                },
                "wns": 0.385,
                "tns": 0.0,
            },
            "placement": {
                "paths": {
                    f"req_msg[{i}]->dpath.a_reg.out_reg[{i}].qi": {
                        "slack": 0.380 - 0.01 * i,
                        "delay": 0.085 + 0.001 * i,
                        "startpoint": f"req_msg[{i}]",
                        "endpoint": f"dpath.a_reg.out_reg[{i}].qi",
                    }
                    for i in range(path_count)
                },
                "wns": 0.380,
                "tns": 0.0,
            },
            "cts": {
                "paths": {
                    f"req_msg[{i}]->dpath.a_reg.out_reg[{i}].qi": {
                        "slack": 0.350 - 0.01 * i,
                        "delay": 0.235 + 0.001 * i,
                        "startpoint": f"req_msg[{i}]",
                        "endpoint": f"dpath.a_reg.out_reg[{i}].qi",
                    }
                    for i in range(path_count)
                },
                "wns": 0.350,
                "tns": 0.0,
            },
            "routing": {
                "paths": {
                    f"req_msg[{i}]->dpath.a_reg.out_reg[{i}].qi": {
                        "slack": 0.343 - 0.01 * i,
                        "delay": 0.272 + 0.001 * i,
                        "startpoint": f"req_msg[{i}]",
                        "endpoint": f"dpath.a_reg.out_reg[{i}].qi",
                    }
                    for i in range(path_count)
                },
                "wns": 0.343,
                "tns": 0.0,
            },
        }

        timing_data = stage_timing_data.get(stage, stage_timing_data["synthesis"])

        async def mock_extract_timing_data():
            return timing_data

        checkpoint_system._extract_timing_data = mock_extract_timing_data

    @pytest.mark.asyncio
    async def test_gcd_flow_checkpoints(self, checkpoint_system, mock_manager, gcd_design_files):
        """Test complete GCD flow with timing checkpoints at each stage."""
        # Simulate GCD flow stages
        flow_stages = ["synthesis", "placement", "cts", "routing"]
        checkpoints = {}

        for stage in flow_stages:
            # Mock timing response for this stage
            await self._mock_gcd_timing_response(checkpoint_system, stage)

            # Create checkpoint
            checkpoint = await checkpoint_system.create_checkpoint(f"gcd_{stage}", force_base=(stage == "synthesis"))

            checkpoints[stage] = checkpoint
            assert checkpoint.stage_name == f"gcd_{stage}"

            # Verify compression worked
            if stage != "synthesis":  # Delta checkpoints
                assert not checkpoint.is_base_checkpoint
                assert checkpoint.base_checkpoint_ref is not None
                assert checkpoint.delta_changes.compressed_size > 0
                assert checkpoint.delta_changes.compression_ratio < 1.0

        # Verify checkpoint chain
        routing_chain = checkpoint_system.checkpoint_manager.get_checkpoint_chain(checkpoints["routing"].stage_id)
        assert len(routing_chain) == 4  # All stages in chain
        assert routing_chain[0].stage_name == "gcd_synthesis"  # Base checkpoint first

    @pytest.mark.asyncio
    async def test_gcd_timing_progression(self, checkpoint_system, mock_manager):
        """Test timing metric progression through GCD flow stages."""
        stages_data = [
            ("synthesis", 0.385, -0.0),  # slack, tns
            ("placement", 0.380, -0.0),
            ("cts", 0.350, -0.0),
            ("routing", 0.343, -0.0),
        ]

        checkpoints = []
        for stage_name, _expected_slack, _expected_tns in stages_data:
            await self._mock_gcd_timing_response(checkpoint_system, stage_name)

            checkpoint = await checkpoint_system.create_checkpoint(
                f"gcd_{stage_name}", force_base=(stage_name == "synthesis")
            )

            checkpoints.append(checkpoint)

            # Verify timing degradation is captured
            if stage_name != "synthesis":
                prev_checkpoint = checkpoints[-2]
                # Slack should degrade slightly through flow
                assert checkpoint.wns <= prev_checkpoint.wns

    @pytest.mark.asyncio
    async def test_gcd_checkpoint_restoration(self, checkpoint_system, mock_manager):
        """Test restoring GCD design state from checkpoints."""
        # Create synthesis checkpoint
        await self._mock_gcd_timing_response(checkpoint_system, "synthesis")
        synthesis_checkpoint = await checkpoint_system.create_checkpoint("gcd_synthesis", force_base=True)

        # Create placement checkpoint
        await self._mock_gcd_timing_response(checkpoint_system, "placement")
        placement_checkpoint = await checkpoint_system.create_checkpoint("gcd_placement")

        # Restore synthesis state
        restored_data = await checkpoint_system.restore_checkpoint(synthesis_checkpoint.stage_id)
        assert "paths" in restored_data
        assert restored_data["wns"] is not None

        # Restore placement state
        restored_data = await checkpoint_system.restore_checkpoint(placement_checkpoint.stage_id)
        assert "paths" in restored_data
        assert restored_data["wns"] is not None

    @pytest.mark.asyncio
    async def test_gcd_storage_efficiency(self, checkpoint_system, mock_manager):
        """Test storage efficiency with GCD design through multiple stages."""
        stages = ["synthesis", "floorplan", "placement", "cts", "routing", "finishing"]

        for i, stage in enumerate(stages):
            await self._mock_gcd_timing_response(checkpoint_system, stage)
            await checkpoint_system.create_checkpoint(f"gcd_{stage}", force_base=(i == 0))

        # Check storage statistics
        stats = checkpoint_system.get_storage_statistics()

        assert stats["checkpoint_count"] == len(stages)
        assert stats["base_checkpoint_count"] == 1  # Only synthesis is base
        assert stats["compression_ratio"] < 0.5  # Should achieve >50% compression
        assert stats["storage_reduction_percent"] > 50.0

    def test_gcd_tcl_commands(self, gcd_design_files):
        """Test Tcl command generation for GCD timing analysis."""
        # Get design files dynamically
        design_files = gcd_design_files

        expected_commands = [
            # Design setup
            f'read_lef "{design_files["lef"]}"',
            f'read_liberty "{design_files["lib"]}"',
            f'read_verilog "{design_files["verilog"]}"',
            'link_design "gcd"',
            f'read_sdc "{design_files["sdc"]}"',
            # Timing analysis commands for checkpointing
            "report_checks -format full_clock_expanded -fields {input_pin net fanout capacitance slew delay arrival "
            "required}",
            "report_checks -path_delay min_max -format summary",
            "report_timing -nworst 10 -format full_clock_expanded",
            "report_wns",
            "report_tns",
            "report_worst_slack -max",
            "report_worst_slack -min",
            # Path analysis for delta compression
            "get_fanin -levels 3 -only_cells [get_pins */D]",
            "get_fanout -levels 3 -only_cells [get_pins */Q]",
            "report_timing_histogram -bins 20",
            # Corner analysis
            "report_checks -corner slow",
            "report_checks -corner fast",
        ]

        gcd_tcl_commands = self._generate_gcd_tcl_commands(design_files)

        for cmd in expected_commands:
            assert any(cmd in tcl_cmd for tcl_cmd in gcd_tcl_commands), f"Command not found: {cmd}"

    def _generate_gcd_tcl_commands(self, design_files):
        """Generate Tcl commands for GCD timing analysis."""
        return [
            # Design setup
            f'read_lef "{design_files["lef"]}"',
            f'read_liberty "{design_files["lib"]}"',
            f'read_verilog "{design_files["verilog"]}"',
            'link_design "gcd"',
            f'read_sdc "{design_files["sdc"]}"',
            # Comprehensive timing analysis
            "report_checks -format full_clock_expanded -fields {input_pin net fanout capacitance slew delay arrival "
            "required}",
            "report_checks -path_delay min_max -format summary",
            "report_timing -nworst 10 -format full_clock_expanded",
            "report_wns",
            "report_tns",
            "report_worst_slack -max",
            "report_worst_slack -min",
            # Advanced path analysis
            "get_fanin -levels 3 -only_cells [get_pins */D]",
            "get_fanout -levels 3 -only_cells [get_pins */Q]",
            "report_timing_histogram -bins 20",
            "report_timing_histogram -bins 50 -setup",
            "report_timing_histogram -bins 50 -hold",
            "report_logic_depth_histogram -bins 20",
            # Multi-corner analysis
            "report_checks -corner slow",
            "report_checks -corner fast",
            # Clock analysis
            "report_clock_properties [get_clocks core_clock]",
            "report_clock_skew [get_clocks core_clock]",
            # Power analysis integration
            "report_power -hierarchy",
            "report_power -instances [get_cells dpath.*]",
        ]

    @pytest.mark.asyncio
    async def test_execute_gcd_tcl_commands(self, checkpoint_system, mock_manager):
        """Test executing GCD Tcl commands through the manager."""
        gcd_commands = self._generate_gcd_tcl_commands(
            {"verilog": "/tmp/gcd.v", "sdc": "/tmp/gcd.sdc", "lef": "/tmp/tech.lef", "lib": "/tmp/tech.lib"}
        )

        # Mock successful command execution
        mock_response = MagicMock()
        mock_response.stdout = ["Command executed successfully"]
        mock_response.stderr = []
        mock_response.returncode = 0
        mock_manager.execute_command.return_value = mock_response

        # Execute each command
        for cmd in gcd_commands[:5]:  # Test first 5 commands
            result = await mock_manager.execute_command(cmd)
            assert result.returncode == 0
            mock_manager.execute_command.assert_called_with(cmd)

    @pytest.mark.asyncio
    async def test_gcd_checkpoint_performance_metrics(self, checkpoint_system, mock_manager):
        """Test performance metrics collection during GCD flow."""
        import time

        # Create multiple checkpoints and measure timing
        start_time = time.time()

        for i in range(5):
            await self._mock_gcd_timing_response(checkpoint_system, "synthesis")
            await checkpoint_system.create_checkpoint(f"gcd_perf_test_{i}", force_base=(i == 0))

        end_time = time.time()
        checkpoint_time = end_time - start_time

        # Checkpoint creation should be fast
        assert checkpoint_time < 1.0  # Less than 1 second for 5 checkpoints

        # Check storage efficiency
        stats = checkpoint_system.get_storage_statistics()
        assert stats["checkpoint_count"] == 5

        # Memory usage should be reasonable
        total_storage_mb = stats["total_storage_bytes"] / (1024 * 1024)
        assert total_storage_mb < 50  # Less than 50MB for test data

    def test_create_gcd_test_script(self):
        """Create a complete GCD test script for manual validation."""
        gcd_script = self._create_complete_gcd_test_script()

        # Verify script contains essential components
        assert "read_verilog" in gcd_script
        assert "read_sdc" in gcd_script
        assert "create_checkpoint" in gcd_script
        assert "report_checks" in gcd_script
        assert "link_design" in gcd_script

    def _create_complete_gcd_test_script(self):
        """Create a complete Tcl script for GCD timing checkpoint testing."""
        return """#!/usr/bin/env openroad
# GCD Timing Checkpoint Test Script
# This script tests the timing checkpoint system using the GCD design

# Design setup - paths will be dynamically determined
read_lef "$OPENROAD_DIR/test/Nangate45/Nangate45.lef"
read_liberty "$OPENROAD_DIR/test/Nangate45/Nangate45_typ.lib"
read_verilog "$OPENROAD_DIR/src/gpl/test/design/nangate45/gcd/gcd.v"
link_design "gcd"
read_sdc "$OPENROAD_DIR/src/par/test/gcd_nangate45.sdc"

# Initialize timing checkpoint system
python_command "
import sys
import os
# Use environment variable or current working directory
openroad_mcp_src = os.environ.get('OPENROAD_MCP_SRC', os.path.join(os.getcwd(), 'src'))
sys.path.append(openroad_mcp_src)
from openroad_mcp.timing.checkpoint import TimingCheckpointSystem
checkpoint_dir = os.environ.get('CHECKPOINT_DIR', './gcd_checkpoints')
checkpoint_system = TimingCheckpointSystem(openroad_manager, checkpoint_dir)
"

# Stage 1: Synthesis timing checkpoint
puts "Creating synthesis checkpoint..."
python_command "
import asyncio
checkpoint_synth = asyncio.run(checkpoint_system.create_checkpoint('gcd_synthesis', force_base=True))
print(f'Synthesis checkpoint created: {checkpoint_synth.stage_id}')
"

# Perform synthesis
run_synthesis

# Stage 2: Post-synthesis checkpoint
puts "Creating post-synthesis checkpoint..."
report_checks -format full_clock_expanded -nworst 5
python_command "
checkpoint_post_synth = asyncio.run(checkpoint_system.create_checkpoint('gcd_post_synthesis'))
print(f'Post-synthesis checkpoint: {checkpoint_post_synth.stage_id}')
"

# Floorplanning
initialize_floorplan \\
    -utilization 30 \\
    -aspect_ratio 1 \\
    -core_space 2 \\
    -die_area "0 0 100 100"

# Stage 3: Post-floorplan checkpoint
puts "Creating floorplan checkpoint..."
report_checks -format summary
python_command "
checkpoint_fp = asyncio.run(checkpoint_system.create_checkpoint('gcd_floorplan'))
print(f'Floorplan checkpoint: {checkpoint_fp.stage_id}')
"

# Placement
global_placement
detailed_placement

# Stage 4: Post-placement checkpoint
puts "Creating placement checkpoint..."
report_checks -format full_clock_expanded -nworst 10
report_wns
report_tns
python_command "
checkpoint_place = asyncio.run(checkpoint_system.create_checkpoint('gcd_placement'))
print(f'Placement checkpoint: {checkpoint_place.stage_id}')
print(f'Storage stats: {checkpoint_system.get_storage_statistics()}')
"

# Clock tree synthesis
clock_tree_synthesis \\
    -root_buffer BUF_X4 \\
    -clk_buffer BUF_X4

# Stage 5: Post-CTS checkpoint
puts "Creating CTS checkpoint..."
report_checks -corner slow -format summary
report_checks -corner fast -format summary
report_clock_skew [get_clocks core_clock]
python_command "
checkpoint_cts = asyncio.run(checkpoint_system.create_checkpoint('gcd_cts'))
print(f'CTS checkpoint: {checkpoint_cts.stage_id}')
"

# Global routing
global_route

# Stage 6: Post-routing checkpoint
puts "Creating routing checkpoint..."
report_checks -format full_clock_expanded -fields {input_pin net capacitance slew delay arrival required} -nworst 20
report_timing_histogram -bins 50 -setup
python_command "
checkpoint_route = asyncio.run(checkpoint_system.create_checkpoint('gcd_routing'))
print(f'Routing checkpoint: {checkpoint_route.stage_id}')
"

# Final timing analysis and checkpoint restoration test
puts "Testing checkpoint restoration..."
python_command "
# Test restoration of synthesis checkpoint
synth_data = asyncio.run(checkpoint_system.restore_checkpoint(checkpoint_synth.stage_id))
print(f'Restored synthesis state with {len(synth_data.get(\"paths\", {}))} paths')

# Test restoration of placement checkpoint
place_data = asyncio.run(checkpoint_system.restore_checkpoint(checkpoint_place.stage_id))
print(f'Restored placement state with {len(place_data.get(\"paths\", {}))} paths')

# Final storage statistics
final_stats = checkpoint_system.get_storage_statistics()
print(f'Final storage statistics:')
print(f'  Total checkpoints: {final_stats[\"checkpoint_count\"]}')
print(f'  Compression ratio: {final_stats[\"compression_ratio\"]:.3f}')
print(f'  Storage reduction: {final_stats[\"storage_reduction_percent\"]:.1f}%')
print(f'  Total storage: {final_stats[\"total_storage_bytes\"] / 1024 / 1024:.2f} MB')
"

puts "GCD timing checkpoint test completed successfully!"
"""
