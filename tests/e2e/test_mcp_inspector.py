"""
E2E tests for MCP server via MCP Inspector + Playwright.

Tests the full MCP flow on both transports (http, stdio) in parallel
using the MCP Inspector UI automated with Playwright.

Requires:
  - playwright: `uv run playwright install chromium`
  - npx + @modelcontextprotocol/inspector (auto-installed via npx)

Run:
  uv run pytest tests/e2e/ -v -s
"""

import asyncio
import os
import subprocess
import time

import pytest
from playwright.async_api import Page, async_playwright

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INSPECTOR_STARTUP_TIMEOUT = 15  # seconds to wait for inspector proxy to start
SERVER_STARTUP_TIMEOUT = 10  # seconds to wait for MCP server to start
HTTP_PORT_STDIO = 6277  # MCP inspector proxy port for stdio transport
HTTP_PORT_HTTP = 6278  # MCP inspector proxy port for http transport
MCP_HTTP_PORT = 8766  # Port for the MCP server HTTP transport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_uv_run_cmd(args: list[str]) -> list[str]:
    """Build a uv run command for the MCP server."""
    return ["uv", "run", "openroad-mcp", *args]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_http_server():
    """Start the MCP server in HTTP transport mode."""
    proc = subprocess.Popen(
        _get_uv_run_cmd(["--transport", "http", "--port", str(MCP_HTTP_PORT)]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )
    assert _wait_for_port("localhost", MCP_HTTP_PORT, SERVER_STARTUP_TIMEOUT), (
        f"MCP HTTP server did not start on port {MCP_HTTP_PORT}"
    )
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def inspector_stdio():
    """Start MCP Inspector proxying a stdio MCP server."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    proc = subprocess.Popen(
        [
            "npx",
            "--yes",
            "@modelcontextprotocol/inspector",
            "--cli",
            *_get_uv_run_cmd(["--transport", "stdio"]),
            "--port",
            str(HTTP_PORT_STDIO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root,
    )
    assert _wait_for_port("localhost", HTTP_PORT_STDIO, INSPECTOR_STARTUP_TIMEOUT), (
        "MCP Inspector (stdio) proxy did not start"
    )
    yield f"http://localhost:{HTTP_PORT_STDIO}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def inspector_http(mcp_http_server):
    """Start MCP Inspector proxying the HTTP MCP server."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    proc = subprocess.Popen(
        [
            "npx",
            "--yes",
            "@modelcontextprotocol/inspector",
            "--cli",
            f"http://localhost:{MCP_HTTP_PORT}",
            "--port",
            str(HTTP_PORT_HTTP),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root,
    )
    assert _wait_for_port("localhost", HTTP_PORT_HTTP, INSPECTOR_STARTUP_TIMEOUT), (
        "MCP Inspector (http) proxy did not start"
    )
    yield f"http://localhost:{HTTP_PORT_HTTP}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Shared test logic
# ---------------------------------------------------------------------------


async def _assert_inspector_tools_visible(page: Page, inspector_url: str) -> None:
    """Open the MCP inspector and verify tools are listed."""
    await page.goto(inspector_url)
    await page.wait_for_load_state("networkidle", timeout=15000)

    # Click on "Tools" tab if present
    tools_tab = page.get_by_role("tab", name="Tools")
    if await tools_tab.count() > 0:
        await tools_tab.click()

    # Expect at least one tool to be listed
    await page.wait_for_selector("[data-testid='tool-item'], .tool-name, li.tool", timeout=10000)
    tool_items = await page.locator("[data-testid='tool-item'], .tool-name, li.tool").count()
    assert tool_items > 0, "No MCP tools found in Inspector UI"


async def _assert_inspector_tool_call(page: Page, inspector_url: str) -> None:
    """Call the list_interactive_sessions tool and verify a response."""
    await page.goto(inspector_url)
    await page.wait_for_load_state("networkidle", timeout=15000)

    # Navigate to Tools tab
    tools_tab = page.get_by_role("tab", name="Tools")
    if await tools_tab.count() > 0:
        await tools_tab.click()

    # Find and click list_interactive_sessions tool
    tool = page.get_by_text("list_interactive_sessions", exact=False).first
    await tool.wait_for(timeout=10000)
    await tool.click()

    # Execute the tool (no required args)
    run_btn = page.get_by_role("button", name="Run").first
    await run_btn.wait_for(timeout=5000)
    await run_btn.click()

    # Verify response appears
    response = page.locator("[data-testid='tool-response'], .response-content, pre.result")
    await response.wait_for(timeout=10000)
    content = await response.inner_text()
    assert len(content) > 0, "Empty response from list_interactive_sessions"


# ---------------------------------------------------------------------------
# Tests: stdio transport
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_inspector_stdio_tools_visible(inspector_stdio: str) -> None:
    """Verify MCP tools are visible in Inspector when using stdio transport."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await _assert_inspector_tools_visible(page, inspector_stdio)
        finally:
            await browser.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_inspector_stdio_tool_call(inspector_stdio: str) -> None:
    """Call a tool via MCP Inspector using stdio transport and verify response."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await _assert_inspector_tool_call(page, inspector_stdio)
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Tests: http transport
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_inspector_http_tools_visible(inspector_http: str) -> None:
    """Verify MCP tools are visible in Inspector when using HTTP transport."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await _assert_inspector_tools_visible(page, inspector_http)
        finally:
            await browser.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_inspector_http_tool_call(inspector_http: str) -> None:
    """Call a tool via MCP Inspector using HTTP transport and verify response."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await _assert_inspector_tool_call(page, inspector_http)
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Tests: both transports in parallel
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_both_transports_in_parallel(inspector_stdio: str, inspector_http: str) -> None:
    """Run the same tool call test on both transports simultaneously."""

    async def run_transport_test(transport_url: str) -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await _assert_inspector_tools_visible(page, transport_url)
            finally:
                await browser.close()

    await asyncio.gather(
        run_transport_test(inspector_stdio),
        run_transport_test(inspector_http),
    )
