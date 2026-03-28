"""
E2E tests for MCP server.

Two layers of verification:
1. Primary: MCP Python SDK (ClientSession + stdio_client) — tests JSON-RPC protocol directly.
2. Secondary: MCP Inspector CLI — verifies tool compatibility as a second check.

No browser or Playwright needed.

Run:
  uv run pytest tests/e2e/ -v -m e2e
"""

import asyncio
import json
import subprocess
import time

import pytest
import pytest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

MCP_HTTP_PORT = 8766
SERVER_STARTUP_TIMEOUT = 10


def _wait_for_port(host: str, port: int, timeout: float = SERVER_STARTUP_TIMEOUT) -> bool:
    """Poll until a TCP port is open or timeout expires."""
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


@pytest_asyncio.fixture(scope="function")
async def stdio_mcp_client():
    """MCP client session using stdio transport."""
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "openroad-mcp", "--transport", "stdio"],
        env=None,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.fixture(scope="function")
def http_mcp_server():
    """Start the MCP server in HTTP transport mode."""
    proc = subprocess.Popen(
        ["uv", "run", "openroad-mcp", "--transport", "http", "--port", str(MCP_HTTP_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_port("localhost", MCP_HTTP_PORT):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise RuntimeError(f"MCP HTTP server did not start on port {MCP_HTTP_PORT}")
    except Exception:
        proc.kill()
        raise
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest_asyncio.fixture(scope="function")
async def http_mcp_client(http_mcp_server):
    """MCP client session using HTTP (streamable) transport."""
    async with streamablehttp_client(f"http://localhost:{MCP_HTTP_PORT}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_tools_listed(stdio_mcp_client: ClientSession) -> None:
    """Verify tools are returned over stdio transport."""
    result = await stdio_mcp_client.list_tools()
    assert len(result.tools) > 0, "No MCP tools returned over stdio"
    tool_names = [t.name for t in result.tools]
    assert "list_interactive_sessions" in tool_names


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stdio_tool_call(stdio_mcp_client: ClientSession) -> None:
    """Call list_interactive_sessions over stdio and verify response schema."""
    result = await stdio_mcp_client.call_tool("list_interactive_sessions", {})
    assert result is not None
    assert result.content is not None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_http_tools_listed(http_mcp_client: ClientSession) -> None:
    """Verify tools are returned over HTTP transport."""
    result = await http_mcp_client.list_tools()
    assert len(result.tools) > 0, "No MCP tools returned over HTTP"
    tool_names = [t.name for t in result.tools]
    assert "list_interactive_sessions" in tool_names


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_http_tool_call(http_mcp_client: ClientSession) -> None:
    """Call list_interactive_sessions over HTTP and verify response schema."""
    result = await http_mcp_client.call_tool("list_interactive_sessions", {})
    assert result is not None
    assert result.content is not None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_both_transports_in_parallel(
    stdio_mcp_client: ClientSession, http_mcp_client: ClientSession
) -> None:
    """Run tool listing on both transports simultaneously."""
    stdio_result, http_result = await asyncio.gather(
        stdio_mcp_client.list_tools(),
        http_mcp_client.list_tools(),
    )
    assert len(stdio_result.tools) > 0
    assert len(http_result.tools) > 0
    stdio_names = {t.name for t in stdio_result.tools}
    http_names = {t.name for t in http_result.tools}
    assert stdio_names == http_names, (
        f"Tool mismatch between transports: stdio={stdio_names}, http={http_names}"
    )


# ---------------------------------------------------------------------------
# Secondary: MCP Inspector CLI verification
# ---------------------------------------------------------------------------

def _run_inspector_cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run MCP Inspector CLI and return the completed process."""
    return subprocess.run(
        ["npx", "--yes", "@modelcontextprotocol/inspector", "--cli", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.e2e
def test_inspector_cli_tools_list() -> None:
    """Use Inspector CLI to verify tool list is returned (tool compatibility check)."""
    result = _run_inspector_cli(
        "--method", "tools/list",
        "uv", "run", "openroad-mcp",
    )
    assert result.returncode == 0, f"Inspector CLI failed:\n{result.stderr}"
    data = json.loads(result.stdout)
    assert "tools" in data, "Inspector CLI response missing 'tools' key"
    tool_names = [t["name"] for t in data["tools"]]
    assert len(tool_names) > 0, "Inspector CLI returned no tools"
    assert "list_interactive_sessions" in tool_names


@pytest.mark.e2e
def test_inspector_cli_tool_call() -> None:
    """Use Inspector CLI to call list_interactive_sessions and verify response."""
    result = _run_inspector_cli(
        "--method", "tools/call",
        "--tool-name", "list_interactive_sessions",
        "uv", "run", "openroad-mcp",
    )
    assert result.returncode == 0, f"Inspector CLI tool call failed:\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data.get("isError") is False, f"Tool call returned error: {data}"
    assert "content" in data, "Inspector CLI response missing 'content' key"
    assert len(data["content"]) > 0, "Inspector CLI returned empty content"
