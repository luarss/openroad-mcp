"""Integration tests for OpenROAD timing analysis workflows."""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from openroad_mcp.interactive.session_manager import SessionManager


class TestTimingAnalysisWorkflows:
    """Integration tests for timing analysis workflows."""

    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            # Create mock design files
            (workspace / "design.v").write_text("""
module simple_adder (
    input wire clk,
    input wire [7:0] a,
    input wire [7:0] b,
    output reg [8:0] sum
);
    always @(posedge clk) begin
        sum <= a + b;
    end
endmodule
""")

            # Create mock SDC constraints
            (workspace / "constraints.sdc").write_text("""
create_clock -period 10.0 [get_ports clk]
set_input_delay 2.0 -clock clk [get_ports {a b}]
set_output_delay 2.0 -clock clk [get_ports sum]
""")

            # Create mock technology library info
            (workspace / "tech_lib.lib").write_text("""
library(test_lib) {
    delay_model : table_lookup;
    time_unit : "1ns";
    voltage_unit : "1V";
    current_unit : "1mA";
    // Simplified library for testing
}
""")

            yield workspace

    async def test_basic_timing_analysis_workflow(self, temp_workspace):
        """Test basic timing analysis workflow."""
        session_manager = SessionManager()

        try:
            # Create interactive session
            session_id = await session_manager.create_session(cwd=str(temp_workspace), buffer_size=2048)

            # Mock OpenROAD commands and responses
            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):
                # Define mock responses for different commands
                def mock_read_side_effect(*args, **kwargs):
                    from unittest.mock import AsyncMock

                    result = AsyncMock()

                    # Check what command was last sent
                    if mock_send.call_args:
                        command = mock_send.call_args[0][0]

                        if "read_verilog" in command:
                            result.output = "Reading Verilog file: design.v\nModule simple_adder loaded successfully"
                        elif "read_sdc" in command:
                            result.output = (
                                "Reading SDC constraints from constraints.sdc\nConstraints loaded: 3 timing constraints"
                            )
                        elif "create_clock" in command:
                            result.output = "Clock 'clk' created with period 10.0ns"
                        elif "report_timing" in command:
                            result.output = """
Startpoint: a[0] (input port clocked by clk)
Endpoint: sum[0] (output port clocked by clk)
Path Group: clk
Path Type: max

  Delay    Time   Description
  --------------------------------------------------------
   0.000   0.000   input external delay
   1.250   1.250   a[0] (in)
   2.150   3.400   simple_adder/add_inst/sum[0] (combinational)
   0.500   3.900   sum[0] (out)

Data arrival time: 3.900
Data required time: 8.000
Slack (MET): 4.100ns
"""
                        elif "report_checks" in command:
                            result.output = """
Setup Check Summary:
  Worst Slack: 4.100ns (MET)
  Total Negative Slack: 0.000ns
  Number of Failing Endpoints: 0

Hold Check Summary:
  Worst Slack: 0.500ns (MET)
  Total Negative Slack: 0.000ns
  Number of Failing Endpoints: 0
"""
                        elif "report_power" in command:
                            result.output = """
Power Report:
  Total Power: 15.234 mW
  Dynamic Power: 12.156 mW
  Static Power: 3.078 mW
"""
                        else:
                            result.output = f"Command executed: {command}"
                    else:
                        result.output = "Command executed successfully"

                    result.session_id = session_id
                    result.execution_time = 0.1
                    result.command_count = mock_send.call_count
                    return result

                mock_read.side_effect = mock_read_side_effect

                # Execute timing analysis workflow
                workflow_steps = [
                    "read_verilog design.v",
                    "read_sdc constraints.sdc",
                    "create_clock -period 10.0 [get_ports clk]",
                    "report_timing -max_paths 10",
                    "report_checks -path_delay max",
                    "report_checks -path_delay min",
                    "report_power",
                ]

                results = []
                for step in workflow_steps:
                    result = await session_manager.execute_command(session_id, step)
                    results.append(result)

                    # Verify each step completed
                    assert result.session_id == session_id
                    assert len(result.output) > 0
                    print(f"Step: {step}")
                    print(f"Output: {result.output[:100]}...")

                # Verify workflow completed successfully
                assert len(results) == len(workflow_steps)
                assert all(r.execution_time >= 0 for r in results)

                # Verify timing-specific outputs
                timing_result = results[3]  # report_timing result
                assert "Slack" in timing_result.output
                assert "Delay" in timing_result.output

                checks_result = results[4]  # report_checks result
                assert "Setup Check" in checks_result.output
                assert "Hold Check" in checks_result.output

                power_result = results[6]  # report_power result
                assert "Power" in power_result.output
                assert "mW" in power_result.output

        finally:
            await session_manager.cleanup_all()

    async def test_multi_corner_timing_analysis(self, temp_workspace):
        """Test multi-corner timing analysis workflow."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session(cwd=str(temp_workspace))

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):

                def mock_multi_corner_response(*args, **kwargs):
                    from unittest.mock import AsyncMock

                    result = AsyncMock()

                    if mock_send.call_args:
                        command = mock_send.call_args[0][0]

                        if "create_corner" in command:
                            if "slow" in command:
                                result.output = "Corner 'slow' created: temp=125C, voltage=0.9V"
                            elif "fast" in command:
                                result.output = "Corner 'fast' created: temp=-40C, voltage=1.1V"
                            else:
                                result.output = "Corner 'typical' created: temp=25C, voltage=1.0V"
                        elif "set_operating_conditions" in command:
                            result.output = "Operating conditions set for current corner"
                        elif "report_timing" in command and "corner" in command:
                            if "slow" in command:
                                result.output = """
Corner: slow
Worst Slack: 2.100ns (MET)
Critical Path Delay: 7.900ns
"""
                            elif "fast" in command:
                                result.output = """
Corner: fast
Worst Slack: 6.500ns (MET)
Critical Path Delay: 3.500ns
"""
                            else:
                                result.output = """
Corner: typical
Worst Slack: 4.100ns (MET)
Critical Path Delay: 5.900ns
"""
                        else:
                            result.output = f"Multi-corner command executed: {command}"

                    result.session_id = session_id
                    result.execution_time = 0.15
                    result.command_count = mock_send.call_count
                    return result

                mock_read.side_effect = mock_multi_corner_response

                # Multi-corner workflow
                corners = ["typical", "slow", "fast"]
                corner_results = {}

                for corner in corners:
                    # Create corner
                    await session_manager.execute_command(session_id, f"create_corner {corner}")

                    # Set operating conditions
                    await session_manager.execute_command(session_id, f"set_operating_conditions -{corner}")

                    # Run timing analysis for this corner
                    result = await session_manager.execute_command(
                        session_id, f"report_timing -corner {corner} -max_paths 1"
                    )

                    corner_results[corner] = result
                    assert corner in result.output
                    assert "Slack" in result.output

                # Verify all corners analyzed
                assert len(corner_results) == 3
                for corner, result in corner_results.items():
                    assert corner in result.output
                    print(f"Corner {corner}: {result.output[:50]}...")

        finally:
            await session_manager.cleanup_all()

    async def test_what_if_analysis_workflow(self, temp_workspace):
        """Test what-if analysis workflow with constraint changes."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session(cwd=str(temp_workspace))

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):
                scenario_counter = 0

                def mock_what_if_response(*args, **kwargs):
                    nonlocal scenario_counter
                    from unittest.mock import AsyncMock

                    result = AsyncMock()

                    if mock_send.call_args:
                        command = mock_send.call_args[0][0]

                        if "create_clock" in command:
                            if "5.0" in command:  # Aggressive clock
                                result.output = "Clock period set to 5.0ns (200MHz)"
                                scenario_counter = 1
                            elif "15.0" in command:  # Relaxed clock
                                result.output = "Clock period set to 15.0ns (66MHz)"
                                scenario_counter = 2
                            else:  # Original 10.0ns
                                result.output = "Clock period set to 10.0ns (100MHz)"
                                scenario_counter = 0
                        elif "report_timing" in command:
                            if scenario_counter == 1:  # Aggressive
                                result.output = """
Aggressive Scenario (5.0ns):
Worst Slack: -1.100ns (VIOLATED)
Critical Path Delay: 6.100ns
Number of Failing Paths: 5
"""
                            elif scenario_counter == 2:  # Relaxed
                                result.output = """
Relaxed Scenario (15.0ns):
Worst Slack: 8.900ns (MET)
Critical Path Delay: 6.100ns
Number of Failing Paths: 0
"""
                            else:  # Baseline
                                result.output = """
Baseline Scenario (10.0ns):
Worst Slack: 3.900ns (MET)
Critical Path Delay: 6.100ns
Number of Failing Paths: 0
"""
                        else:
                            result.output = f"What-if command: {command}"

                    result.session_id = session_id
                    result.execution_time = 0.2
                    result.command_count = mock_send.call_count
                    return result

                mock_read.side_effect = mock_what_if_response

                # What-if analysis scenarios
                scenarios = [("baseline", "10.0"), ("aggressive", "5.0"), ("relaxed", "15.0")]

                scenario_results = {}

                for scenario_name, period in scenarios:
                    # Load design for each scenario
                    await session_manager.execute_command(session_id, "read_verilog design.v")

                    # Set clock constraint
                    await session_manager.execute_command(session_id, f"create_clock -period {period} [get_ports clk]")

                    # Run timing analysis
                    result = await session_manager.execute_command(session_id, "report_timing -max_paths 1")

                    scenario_results[scenario_name] = result

                    print(f"Scenario {scenario_name} ({period}ns): {result.output[:60]}...")

                # Verify scenario analysis
                assert len(scenario_results) == 3

                # Baseline should meet timing
                baseline = scenario_results["baseline"]
                assert "MET" in baseline.output

                # Aggressive should fail timing
                aggressive = scenario_results["aggressive"]
                assert "VIOLATED" in aggressive.output or "FAIL" in aggressive.output

                # Relaxed should easily meet timing
                relaxed = scenario_results["relaxed"]
                assert "MET" in relaxed.output

        finally:
            await session_manager.cleanup_all()

    async def test_hierarchical_timing_analysis(self, temp_workspace):
        """Test hierarchical timing analysis workflow."""
        session_manager = SessionManager()

        # Create hierarchical design files
        (temp_workspace / "top_module.v").write_text("""
module top_module (
    input wire clk,
    input wire reset,
    input wire [15:0] data_in,
    output wire [15:0] data_out
);
    wire [15:0] stage1_out, stage2_out;

    pipeline_stage stage1 (.clk(clk), .reset(reset), .in(data_in), .out(stage1_out));
    pipeline_stage stage2 (.clk(clk), .reset(reset), .in(stage1_out), .out(stage2_out));
    pipeline_stage stage3 (.clk(clk), .reset(reset), .in(stage2_out), .out(data_out));
endmodule
""")

        (temp_workspace / "pipeline_stage.v").write_text("""
module pipeline_stage (
    input wire clk,
    input wire reset,
    input wire [15:0] in,
    output reg [15:0] out
);
    always @(posedge clk or posedge reset) begin
        if (reset)
            out <= 16'h0000;
        else
            out <= in + 16'h0001;  // Simple increment
    end
endmodule
""")

        try:
            session_id = await session_manager.create_session(cwd=str(temp_workspace))

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):

                def mock_hierarchical_response(*args, **kwargs):
                    from unittest.mock import AsyncMock

                    result = AsyncMock()

                    if mock_send.call_args:
                        command = mock_send.call_args[0][0]

                        if "read_verilog" in command:
                            if "top_module" in command:
                                result.output = "Loaded top_module with 3 pipeline_stage instances"
                            else:
                                result.output = "Loaded pipeline_stage module"
                        elif "report_timing" in command:
                            if "-through" in command:
                                result.output = """
Hierarchical Path Analysis:
Instance: top_module/stage1
  Input to Output Delay: 2.5ns
  Slack: 7.5ns (MET)

Instance: top_module/stage2
  Input to Output Delay: 2.5ns
  Slack: 5.0ns (MET)

Instance: top_module/stage3
  Input to Output Delay: 2.5ns
  Slack: 2.5ns (MET)
"""
                            else:
                                result.output = """
Top-level Timing Report:
  Overall Pipeline Delay: 7.5ns
  Worst Slack: 2.5ns (MET)
  Critical Path: data_in -> stage1 -> stage2 -> stage3 -> data_out
"""
                        elif "report_hierarchy" in command:
                            result.output = """
Design Hierarchy:
top_module
  ├── stage1 (pipeline_stage)
  ├── stage2 (pipeline_stage)
  └── stage3 (pipeline_stage)
"""
                        else:
                            result.output = f"Hierarchical command: {command}"

                    result.session_id = session_id
                    result.execution_time = 0.3
                    result.command_count = mock_send.call_count
                    return result

                mock_read.side_effect = mock_hierarchical_response

                # Hierarchical analysis workflow
                workflow = [
                    "read_verilog pipeline_stage.v",
                    "read_verilog top_module.v",
                    "create_clock -period 10.0 [get_ports clk]",
                    "report_hierarchy",
                    "report_timing -from data_in -to data_out",
                    "report_timing -through top_module/stage1/*",
                    "report_timing -through top_module/stage2/*",
                    "report_timing -through top_module/stage3/*",
                ]

                results = []
                for step in workflow:
                    result = await session_manager.execute_command(session_id, step)
                    results.append(result)
                    print(f"Hierarchical step: {step[:40]}...")

                # Verify hierarchical analysis
                assert len(results) == len(workflow)

                # Check hierarchy report
                hierarchy_result = results[3]
                assert "top_module" in hierarchy_result.output
                assert "stage1" in hierarchy_result.output

                # Check instance-specific timing
                for i in range(5, 8):  # stage timing reports
                    stage_result = results[i]
                    assert "stage" in stage_result.output
                    assert "Delay" in stage_result.output

        finally:
            await session_manager.cleanup_all()

    async def test_concurrent_timing_sessions(self, temp_workspace):
        """Test concurrent timing analysis sessions."""
        session_manager = SessionManager()

        try:
            # Create multiple concurrent sessions
            session_count = 5
            session_ids = []

            for _i in range(session_count):
                session_id = await session_manager.create_session(cwd=str(temp_workspace), buffer_size=1024)
                session_ids.append(session_id)

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):

                def mock_concurrent_response(*args, **kwargs):
                    from unittest.mock import AsyncMock

                    result = AsyncMock()

                    if mock_send.call_args:
                        command = mock_send.call_args[0][0]
                        session_index = (
                            len([call for call in mock_send.call_args_list if call[0][0] == command]) % session_count
                        )

                        if "read_verilog" in command:
                            result.output = f"Session {session_index}: Design loaded"
                        elif "report_timing" in command:
                            result.output = f"""
Session {session_index} Timing Report:
  Worst Slack: {3.0 + session_index * 0.5:.1f}ns (MET)
  Critical Path Delay: {6.0 - session_index * 0.2:.1f}ns
"""
                        else:
                            result.output = f"Session {session_index}: {command}"

                    result.session_id = session_ids[session_index % len(session_ids)]
                    result.execution_time = 0.1 + (session_index * 0.01)
                    result.command_count = mock_send.call_count
                    return result

                mock_read.side_effect = mock_concurrent_response

                # Run concurrent timing analysis
                async def run_session_analysis(session_id, session_index):
                    commands = [
                        "read_verilog design.v",
                        f"create_clock -period {8.0 + session_index} [get_ports clk]",
                        "report_timing -max_paths 1",
                    ]

                    session_results = []
                    for cmd in commands:
                        result = await session_manager.execute_command(session_id, cmd)
                        session_results.append(result)
                        # Small delay to simulate real work
                        await asyncio.sleep(0.01)

                    return session_results

                # Execute concurrent analyses
                tasks = []
                for i, session_id in enumerate(session_ids):
                    task = run_session_analysis(session_id, i)
                    tasks.append(task)

                all_results = await asyncio.gather(*tasks)

                # Verify concurrent execution
                assert len(all_results) == session_count

                for i, session_results in enumerate(all_results):
                    assert len(session_results) == 3  # 3 commands per session

                    # Check timing result
                    timing_result = session_results[2]
                    assert f"Session {i}" in timing_result.output
                    assert "Slack" in timing_result.output

                    print(f"Concurrent session {i}: {timing_result.output[:50]}...")

        finally:
            await session_manager.cleanup_all()


@pytest.mark.asyncio
class TestRealOpenROADIntegration:
    """Tests that could run with real OpenROAD (if available)."""

    @pytest.mark.skipif(not os.getenv("OPENROAD_AVAILABLE"), reason="Real OpenROAD not available")
    async def test_real_openroad_session(self):
        """Test with real OpenROAD binary (skipped unless OPENROAD_AVAILABLE=1)."""
        session_manager = SessionManager()

        try:
            # This would run with real OpenROAD
            session_id = await session_manager.create_session(command=["openroad", "-no_init"], buffer_size=4096)

            # Basic connectivity test
            result = await session_manager.execute_command(
                session_id, 'puts "OpenROAD session active"', timeout_ms=5000
            )

            assert "OpenROAD session active" in result.output
            assert result.session_id == session_id

        finally:
            await session_manager.cleanup_all()

    @pytest.mark.skipif(not os.getenv("OPENROAD_AVAILABLE"), reason="Real OpenROAD not available")
    async def test_real_timing_commands(self):
        """Test real timing commands (skipped unless OPENROAD_AVAILABLE=1)."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session(command=["openroad", "-no_init"])

            # Test basic timing commands
            commands = [
                "help",
                "version",
                'puts "Testing OpenROAD timing commands"',
                # Could add real timing commands here if test data available
            ]

            for cmd in commands:
                result = await session_manager.execute_command(session_id, cmd)
                assert len(result.output) > 0
                print(f"Real OpenROAD: {cmd} -> {result.output[:50]}...")

        finally:
            await session_manager.cleanup_all()


if __name__ == "__main__":
    # Allow running integration tests directly
    pytest.main([__file__, "-v", "-s"])
