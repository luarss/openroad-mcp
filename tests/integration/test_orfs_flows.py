"""Integration tests for ORFS flows via MCP protocol.

These tests exercise the full MCP server stack with real processes:
- MCP tool discovery and schema validation
- Interactive OpenROAD session lifecycle via MCP client
- Real OpenROAD command execution (requires openroad in PATH)
- ORFS report image tools with real filesystem structure

Run via: make test-integration (requires Docker with OpenROAD installed)
"""

import asyncio
import io
import json
import os
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------

OPENROAD_AVAILABLE = shutil.which("openroad") is not None

skip_if_no_openroad = pytest.mark.skipif(
    not OPENROAD_AVAILABLE,
    reason="openroad binary not found in PATH",
)


def get_orfs_flow_path() -> Path:
    """Get ORFS flow path from environment, evaluated at runtime."""
    return Path(os.environ.get("ORFS_FLOW_PATH", "/OpenROAD-flow-scripts/flow"))


skip_if_no_orfs = pytest.mark.skipif(
    not get_orfs_flow_path().exists(),
    reason="ORFS flow path not found",
)

# Expected MCP tools registered by the server
EXPECTED_TOOLS = {
    "interactive_openroad",
    "create_interactive_session",
    "list_interactive_sessions",
    "terminate_interactive_session",
    "inspect_interactive_session",
    "get_session_history",
    "get_session_metrics",
    "list_report_images",
    "read_report_image",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_tool_result(result) -> dict:
    """Extract and parse JSON from an MCP tool call result."""
    assert result.content, "Tool result has no content"
    raw = result.content[0].text
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Test: MCP tool discovery
# ---------------------------------------------------------------------------


class TestMCPToolDiscovery:
    """Verify all expected tools are registered and schemas are sane."""

    async def test_all_tools_registered(self, mcp_client):
        """All expected MCP tools must be discoverable."""
        result = await mcp_client.list_tools()
        registered = {tool.name for tool in result.tools}
        missing = EXPECTED_TOOLS - registered
        assert not missing, f"Missing MCP tools: {missing}"

    async def test_interactive_openroad_schema(self, mcp_client):
        """interactive_openroad tool has required 'command' parameter."""
        result = await mcp_client.list_tools()
        tool = next(t for t in result.tools if t.name == "interactive_openroad")
        params = tool.inputSchema.get("properties", {})
        assert "command" in params, "interactive_openroad must have 'command' parameter"

    async def test_create_session_schema(self, mcp_client):
        """create_interactive_session tool has correct optional parameters."""
        result = await mcp_client.list_tools()
        tool = next(t for t in result.tools if t.name == "create_interactive_session")
        params = tool.inputSchema.get("properties", {})
        # All parameters are optional
        for optional_param in ("session_id", "command", "env", "cwd"):
            assert optional_param in params, f"create_interactive_session missing '{optional_param}'"

    async def test_report_image_tools_schema(self, mcp_client):
        """Report image tools have required platform/design/run_slug parameters."""
        result = await mcp_client.list_tools()
        tools_by_name = {t.name: t for t in result.tools}

        for tool_name in ("list_report_images", "read_report_image"):
            tool = tools_by_name[tool_name]
            params = tool.inputSchema.get("properties", {})
            for required in ("platform", "design", "run_slug"):
                assert required in params, f"{tool_name} missing '{required}'"


# ---------------------------------------------------------------------------
# Test: Session lifecycle via MCP
# ---------------------------------------------------------------------------


class TestSessionLifecycleMCP:
    """Session management through the MCP protocol using bash (always available)."""

    async def test_list_sessions_empty(self, mcp_client):
        """list_interactive_sessions returns valid JSON with no sessions initially."""
        result = await mcp_client.call_tool("list_interactive_sessions", {})
        data = _parse_tool_result(result)
        assert "sessions" in data
        assert "total_count" in data

    async def test_create_bash_session_and_execute(self, mcp_client):
        """Create a bash session, run a command, then terminate it."""
        # Create a session running bash
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        create_data = _parse_tool_result(create_result)
        assert create_data.get("error") is None, f"Session creation failed: {create_data}"
        session_id = create_data["session_id"]
        assert session_id

        try:
            # Execute a command in the session
            exec_result = await mcp_client.call_tool(
                "interactive_openroad",
                {"command": "echo 'integration-test-marker'", "session_id": session_id, "timeout_ms": 5000},
            )
            exec_data = _parse_tool_result(exec_result)
            assert "integration-test-marker" in exec_data.get("output", ""), (
                f"Expected marker in output, got: {exec_data}"
            )
        finally:
            # Terminate the session
            term_result = await mcp_client.call_tool(
                "terminate_interactive_session",
                {"session_id": session_id},
            )
            term_data = _parse_tool_result(term_result)
            assert term_data.get("terminated") is True

    async def test_session_appears_in_list(self, mcp_client):
        """Created session appears in list_interactive_sessions."""
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            list_result = await mcp_client.call_tool("list_interactive_sessions", {})
            list_data = _parse_tool_result(list_result)
            session_ids = [s["session_id"] for s in list_data.get("sessions", [])]
            assert session_id in session_ids, f"Session {session_id} not found in list: {session_ids}"
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id})

    async def test_inspect_session(self, mcp_client):
        """inspect_interactive_session returns structured metrics."""
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            inspect_result = await mcp_client.call_tool(
                "inspect_interactive_session",
                {"session_id": session_id},
            )
            data = _parse_tool_result(inspect_result)
            assert data.get("error") is None, f"Inspect failed: {data}"
            assert "session_id" in data
            assert "metrics" in data
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id})

    async def test_session_history_after_commands(self, mcp_client):
        """get_session_history returns executed commands."""
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            # Execute two commands
            for cmd in ("echo 'first'", "echo 'second'"):
                await mcp_client.call_tool(
                    "interactive_openroad",
                    {"command": cmd, "session_id": session_id, "timeout_ms": 5000},
                )

            history_result = await mcp_client.call_tool(
                "get_session_history",
                {"session_id": session_id},
            )
            history_data = _parse_tool_result(history_result)
            assert history_data.get("error") is None, f"History failed: {history_data}"
            commands = [entry["command"] for entry in history_data.get("history", [])]
            assert "echo 'first'" in commands
            assert "echo 'second'" in commands
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id})

    async def test_session_metrics_aggregation(self, mcp_client):
        """get_session_metrics returns aggregate statistics across sessions."""
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            metrics_result = await mcp_client.call_tool("get_session_metrics", {})
            data = _parse_tool_result(metrics_result)
            assert data.get("error") is None
            metrics = data["metrics"]
            assert "manager" in metrics
            assert metrics["manager"]["active_sessions"] >= 1
            assert "aggregate" in metrics
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id})

    async def test_terminate_nonexistent_session(self, mcp_client):
        """Terminating a non-existent session returns graceful result."""
        result = await mcp_client.call_tool(
            "terminate_interactive_session",
            {"session_id": "nonexistent-session-xyz"},
        )
        data = _parse_tool_result(result)
        # Should report terminated=True with was_alive=False, not raise an exception
        assert "terminated" in data

    async def test_multi_command_execution(self, mcp_client):
        """Execute multiple sequential commands in the same session."""
        create_result = await mcp_client.call_tool(
            "create_interactive_session",
            {"command": ["bash", "--norc", "--noprofile"]},
        )
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            outputs = []
            for i in range(3):
                exec_result = await mcp_client.call_tool(
                    "interactive_openroad",
                    {"command": f"echo 'step-{i}'", "session_id": session_id, "timeout_ms": 5000},
                )
                data = _parse_tool_result(exec_result)
                outputs.append(data.get("output", ""))

            for i, output in enumerate(outputs):
                assert f"step-{i}" in output, f"Step {i} marker missing from output: {output}"
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id})


# ---------------------------------------------------------------------------
# Test: Real OpenROAD session via MCP
# ---------------------------------------------------------------------------


@skip_if_no_openroad
class TestOpenROADSessionMCP:
    """Tests that exercise a real OpenROAD process via the MCP server."""

    async def test_openroad_session_starts(self, mcp_client):
        """OpenROAD session can be created and is alive."""
        create_result = await mcp_client.call_tool("create_interactive_session", {})
        data = _parse_tool_result(create_result)
        assert data.get("error") is None, f"OpenROAD session creation failed: {data}"
        session_id = data["session_id"]
        assert data.get("is_alive") is True

        await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id, "force": True})

    async def test_openroad_tcl_puts(self, mcp_client):
        """Execute a simple Tcl puts command in OpenROAD."""
        create_result = await mcp_client.call_tool("create_interactive_session", {})
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            exec_result = await mcp_client.call_tool(
                "interactive_openroad",
                {"command": 'puts "orfs-integration-test"', "session_id": session_id, "timeout_ms": 15000},
            )
            data = _parse_tool_result(exec_result)
            assert "orfs-integration-test" in data.get("output", ""), f"Expected Tcl puts output, got: {data}"
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id, "force": True})

    async def test_openroad_version_command(self, mcp_client):
        """OpenROAD version command returns a version string."""
        create_result = await mcp_client.call_tool("create_interactive_session", {})
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            exec_result = await mcp_client.call_tool(
                "interactive_openroad",
                {
                    "command": "openroad -version 2>&1 || puts [ord::openroad_version]",
                    "session_id": session_id,
                    "timeout_ms": 15000,
                },
            )
            data = _parse_tool_result(exec_result)
            output = data.get("output", "")
            # OpenROAD outputs a version string like "2.0-..." or similar
            assert output.strip(), f"Expected version output, got empty: {data}"
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id, "force": True})

    async def test_openroad_timing_commands(self, mcp_client):
        """Basic timing-related Tcl commands execute without error."""
        create_result = await mcp_client.call_tool("create_interactive_session", {})
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            # These commands should succeed even without a loaded design
            for cmd in (
                "puts [sta::format_time 1.0 3]",
                "puts [sta::sta_units]",
            ):
                exec_result = await mcp_client.call_tool(
                    "interactive_openroad",
                    {"command": cmd, "session_id": session_id, "timeout_ms": 15000},
                )
                data = _parse_tool_result(exec_result)
                # Output should exist (even if it's an error message the session stays alive)
                assert data.get("session_id") == session_id
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id, "force": True})

    async def test_openroad_session_inspect_metrics(self, mcp_client):
        """Inspect an OpenROAD session returns process memory stats."""
        create_result = await mcp_client.call_tool("create_interactive_session", {})
        session_id = _parse_tool_result(create_result)["session_id"]

        try:
            # Execute one command to populate metrics
            await mcp_client.call_tool(
                "interactive_openroad",
                {"command": 'puts "metric-test"', "session_id": session_id, "timeout_ms": 15000},
            )

            inspect_result = await mcp_client.call_tool(
                "inspect_interactive_session",
                {"session_id": session_id},
            )
            data = _parse_tool_result(inspect_result)
            assert data.get("error") is None
            assert data["metrics"]["commands"]["total_executed"] >= 1
            assert "performance" in data["metrics"]
        finally:
            await mcp_client.call_tool("terminate_interactive_session", {"session_id": session_id, "force": True})


# ---------------------------------------------------------------------------
# Test: ORFS report image tools
# ---------------------------------------------------------------------------


class TestORFSReportImagesMCP:
    """Integration tests for report image tools using real ORFS filesystem paths."""

    @pytest_asyncio.fixture
    async def mcp_client(self, synthetic_orfs_run) -> AsyncGenerator[ClientSession]:
        """Override mcp_client to inject the synthetic ORFS path into the server process."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "openroad_mcp.main"],
            env={
                "ORFS_FLOW_PATH": str(synthetic_orfs_run["root"]),
                "OPENROAD_ENABLE_COMMAND_VALIDATION": "false",
            },
        )
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await asyncio.sleep(1.0)
                    yield session
        except RuntimeError as e:
            if "cancel scope" in str(e).lower():
                pass
            else:
                raise

    @pytest_asyncio.fixture
    async def synthetic_orfs_run(self, tmp_path):
        """Create a synthetic ORFS run directory and configure the server to use it."""
        # Build a minimal ORFS-compatible directory tree
        platform = "nangate45"
        design = "gcd"
        run_slug = "base_20240101_000000"

        run_dir = tmp_path / "reports" / platform / design / run_slug
        run_dir.mkdir(parents=True)

        # Create synthetic webp images for each ORFS stage (valid 1x1 WebP via PIL)
        _buf = io.BytesIO()
        Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_buf, format="WEBP")
        minimal_webp = _buf.getvalue()

        stage_images = [
            "cts_clk.webp",
            "cts_clk_layout.webp",
            "final_all.webp",
            "final_routing.webp",
            "final_congestion.webp",
            "final_placement.webp",
        ]
        for filename in stage_images:
            (run_dir / filename).write_bytes(minimal_webp)

        # Create platforms and designs directories for settings validation
        platforms_dir = tmp_path / "platforms" / platform
        platforms_dir.mkdir(parents=True)
        designs_dir = tmp_path / "designs" / platform / design
        designs_dir.mkdir(parents=True)

        return {
            "root": tmp_path,
            "platform": platform,
            "design": design,
            "run_slug": run_slug,
            "run_dir": run_dir,
            "images": stage_images,
        }

    async def test_list_images_synthetic_run(self, synthetic_orfs_run, mcp_client):
        """list_report_images returns correct image metadata for a synthetic run."""
        r = synthetic_orfs_run
        result = await mcp_client.call_tool(
            "list_report_images",
            {"platform": r["platform"], "design": r["design"], "run_slug": r["run_slug"]},
        )
        data = _parse_tool_result(result)
        assert data.get("error") is None, f"list_report_images failed: {data}"
        assert data["total_images"] == len(r["images"])
        assert "cts" in data["images_by_stage"]
        assert "final" in data["images_by_stage"]

    async def test_list_images_filter_by_stage(self, synthetic_orfs_run, mcp_client):
        """list_report_images can filter by stage."""
        r = synthetic_orfs_run
        result = await mcp_client.call_tool(
            "list_report_images",
            {"platform": r["platform"], "design": r["design"], "run_slug": r["run_slug"], "stage": "final"},
        )
        data = _parse_tool_result(result)
        assert data.get("error") is None
        assert "final" in data["images_by_stage"]
        assert "cts" not in data["images_by_stage"]
        assert data["total_images"] == 4  # final_all, final_routing, final_congestion, final_placement

    async def test_read_image_synthetic_run(self, synthetic_orfs_run, mcp_client):
        """read_report_image returns base64-encoded data and metadata."""
        r = synthetic_orfs_run
        result = await mcp_client.call_tool(
            "read_report_image",
            {
                "platform": r["platform"],
                "design": r["design"],
                "run_slug": r["run_slug"],
                "image_name": "final_all.webp",
            },
        )
        data = _parse_tool_result(result)
        assert data.get("error") is None, f"read_report_image failed: {data}"
        assert data["image_data"] is not None
        metadata = data["metadata"]
        assert metadata["filename"] == "final_all.webp"
        assert metadata["format"] == "webp"
        assert metadata["stage"] == "final"
        assert metadata["type"] == "complete_design"

    async def test_invalid_platform_error(self, synthetic_orfs_run, mcp_client):
        """list_report_images returns ValidationError for unknown platform."""
        r = synthetic_orfs_run
        result = await mcp_client.call_tool(
            "list_report_images",
            {"platform": "unknown_pdk", "design": r["design"], "run_slug": r["run_slug"]},
        )
        data = _parse_tool_result(result)
        assert data["error"] == "ValidationError"
        assert "unknown_pdk" in data["message"]

    async def test_path_traversal_rejected(self, synthetic_orfs_run, mcp_client):
        """Path traversal in run_slug is rejected by the server."""
        r = synthetic_orfs_run
        result = await mcp_client.call_tool(
            "list_report_images",
            {"platform": r["platform"], "design": r["design"], "run_slug": "../../../etc/passwd"},
        )
        data = _parse_tool_result(result)
        assert data["error"] == "ValidationError"


# ---------------------------------------------------------------------------
# Test: ORFS filesystem integration (requires real ORFS installation)
# ---------------------------------------------------------------------------


@skip_if_no_orfs
class TestORFSFilesystemIntegration:
    """Tests that use the real ORFS flow directory structure."""

    async def test_orfs_platforms_discoverable(self, mcp_client):
        """ORFS platforms directory contains expected platforms."""
        orfs_path = get_orfs_flow_path()
        platforms_dir = orfs_path / "platforms"
        assert platforms_dir.exists(), f"ORFS platforms dir not found: {platforms_dir}"
        platforms = [d.name for d in platforms_dir.iterdir() if d.is_dir()]
        assert platforms, "No platforms found in ORFS flow directory"

    async def test_orfs_gcd_design_exists(self, mcp_client):
        """GCD design is present in the ORFS flow directory."""
        orfs_path = get_orfs_flow_path()
        gcd_dir = orfs_path / "designs" / "nangate45" / "gcd"
        assert gcd_dir.exists(), f"GCD design not found at: {gcd_dir}"

    async def test_list_report_images_with_real_orfs_run(self, mcp_client):
        """list_report_images works when a real ORFS run result exists."""
        orfs_path = get_orfs_flow_path()
        reports_dir = orfs_path / "reports" / "nangate45" / "gcd"
        if not reports_dir.exists():
            pytest.skip("No GCD nangate45 ORFS run results found")

        run_slugs = [d.name for d in reports_dir.iterdir() if d.is_dir()]
        if not run_slugs:
            pytest.skip("No run slugs found under GCD nangate45 reports")

        # Find a run slug that has webp images
        run_slug = None
        for slug in sorted(run_slugs):
            webp_files = list((reports_dir / slug).glob("*.webp"))
            if webp_files:
                run_slug = slug
                break

        if run_slug is None:
            pytest.skip("No webp images found in any GCD nangate45 run")

        result = await mcp_client.call_tool(
            "list_report_images",
            {"platform": "nangate45", "design": "gcd", "run_slug": run_slug},
        )
        data = _parse_tool_result(result)
        assert data.get("error") is None, f"list_report_images failed: {data}"
        assert data["total_images"] > 0
