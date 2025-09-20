"""Integration tests for OpenROAD timing analysis workflows."""

import tempfile
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.types import TextContent


@pytest.mark.asyncio
class TestNonInteractiveTimingWorkflows:
    """Integration tests for timing analysis workflows using non-interactive execute_openroad_command."""

    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            yield workspace

    async def test_basic_timing_analysis_workflow(self, temp_workspace, mcp_client: ClientSession):
        """Test basic timing analysis workflow using actual OpenROAD commands."""

        # Execute basic OpenROAD workflow commands that don't require external files
        workflow_steps = [
            'puts "Starting integration test"',
            "help",
            "version",
            'puts "Testing command execution"',
            'puts "Integration test complete"',
        ]

        results = []
        for step in workflow_steps:
            response = await mcp_client.call_tool(
                name="execute_openroad_command", arguments={"command": step, "timeout": 5.0}
            )

            # Extract text content from response
            output = ""
            for content_item in response.content:
                if isinstance(content_item, TextContent):
                    output = content_item.text
                    break

            results.append(output)

            # Verify each step completed
            assert len(output) > 0
            print(f"Step: {step}")
            print(f"Output: {output[:100]}...")

        # Verify workflow completed successfully
        assert len(results) == len(workflow_steps)

        # Verify basic command outputs contain expected content
        help_result = results[1]  # help result
        assert "help" in help_result.lower() or "command" in help_result.lower()

        version_result = results[2]  # version result
        assert "openroad" in version_result.lower() or "version" in version_result.lower()

    async def test_command_sequence_execution(self, temp_workspace, mcp_client: ClientSession):
        """Test sequential command execution."""

        # Test sequence of basic commands
        commands = [
            'puts "Command 1"',
            'puts "Command 2"',
            'puts "Command 3"',
        ]

        for i, cmd in enumerate(commands):
            response = await mcp_client.call_tool(
                name="execute_openroad_command", arguments={"command": cmd, "timeout": 5.0}
            )

            # Extract text content
            output = ""
            for content_item in response.content:
                if isinstance(content_item, TextContent):
                    output = content_item.text
                    break

            assert len(output) > 0
            assert f"Command {i + 1}" in output
            print(f"Sequential command {i + 1}: {output[:50]}...")

    async def test_concurrent_timing_requests(self, temp_workspace, mcp_client: ClientSession):
        """Test concurrent timing analysis requests to single OpenROAD process."""
        import asyncio

        # Run concurrent basic command requests
        async def run_command_sequence(sequence_id):
            commands = [
                f'puts "Concurrent sequence {sequence_id} - step 1"',
                f'puts "Concurrent sequence {sequence_id} - step 2"',
                f'puts "Concurrent sequence {sequence_id} - step 3"',
            ]

            results = []
            for cmd in commands:
                response = await mcp_client.call_tool(
                    name="execute_openroad_command", arguments={"command": cmd, "timeout": 5.0}
                )

                # Extract text content
                output = ""
                for content_item in response.content:
                    if isinstance(content_item, TextContent):
                        output = content_item.text
                        break

                results.append(output)
                # Small delay to simulate real work
                await asyncio.sleep(0.01)

            return results

        # Execute concurrent sequences
        sequence_count = 3
        tasks = []
        for i in range(sequence_count):
            task = run_command_sequence(i)
            tasks.append(task)

        all_results = await asyncio.gather(*tasks)

        # Verify concurrent execution
        assert len(all_results) == sequence_count

        for i, sequence_results in enumerate(all_results):
            assert len(sequence_results) == 3  # 3 commands per sequence

            # Check each result contains the sequence identifier
            for j, result in enumerate(sequence_results):
                assert f"sequence {i}" in result.lower()
                assert f"step {j + 1}" in result.lower()

            print(f"Concurrent sequence {i}: {len(sequence_results)} commands executed")


@pytest.mark.asyncio
class TestRealNonInteractiveOpenROAD:
    """Tests that could run with real OpenROAD using non-interactive approach (if available)."""

    async def test_real_openroad_connection(self, mcp_client: ClientSession):
        """Test with real OpenROAD binary using execute_openroad_command."""

        # Basic connectivity test
        response = await mcp_client.call_tool(
            name="execute_openroad_command",
            arguments={"command": 'puts "OpenROAD non-interactive test"', "timeout": 5.0},
        )

        # Extract text content
        output = ""
        for content_item in response.content:
            if isinstance(content_item, TextContent):
                output = content_item.text
                break

        # Check that we got some response
        assert len(output) > 0
        assert "OpenROAD non-interactive test" in output
        print(f"Real OpenROAD output: {output[:100]}...")

    async def test_real_openroad_basic_commands(self, mcp_client: ClientSession):
        """Test basic OpenROAD commands using non-interactive approach."""

        # Test basic commands
        commands = [
            "help",
            "version",
            'puts "Testing OpenROAD non-interactive commands"',
        ]

        for cmd in commands:
            response = await mcp_client.call_tool(
                name="execute_openroad_command", arguments={"command": cmd, "timeout": 5.0}
            )

            # Extract text content
            output = ""
            for content_item in response.content:
                if isinstance(content_item, TextContent):
                    output = content_item.text
                    break

            assert len(output) > 0
            print(f"Real OpenROAD {cmd}: {output[:50]}...")


if __name__ == "__main__":
    # Allow running integration tests directly
    pytest.main([__file__, "-v", "-s"])
