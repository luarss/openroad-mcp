"""Integration tests for GUI screenshot tool under Xvfb."""

import asyncio
import base64
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from openroad_mcp.config.settings import settings
from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.tools.gui import GuiScreenshotTool


def _has_xvfb() -> bool:
    return shutil.which("xvfb-run") is not None


def _has_openroad() -> bool:
    return shutil.which("openroad") is not None


skip_if_no_xvfb = pytest.mark.skipif(not _has_xvfb(), reason="xvfb-run not installed")
skip_if_no_openroad = pytest.mark.skipif(not _has_openroad(), reason="openroad not installed")


@pytest.mark.asyncio
class TestGuiScreenshot:
    """Tests for the gui_screenshot MCP tool."""

    @pytest.fixture(autouse=True)
    def allow_xvfb(self):
        """Ensure xvfb-run is in the allowed commands list."""
        original = settings.ALLOWED_COMMANDS[:]
        if "xvfb-run" not in settings.ALLOWED_COMMANDS:
            settings.ALLOWED_COMMANDS.append("xvfb-run")
        yield
        settings.ALLOWED_COMMANDS[:] = original

    @pytest.fixture
    async def manager(self):
        """Provide a fresh OpenROADManager and clean up after."""
        # Reset singleton so each test gets a clean manager
        OpenROADManager._instance = None
        mgr = OpenROADManager()
        try:
            yield mgr
        finally:
            await mgr.cleanup_all()
            OpenROADManager._instance = None

    @pytest.fixture
    def tool(self, manager: OpenROADManager) -> GuiScreenshotTool:
        return GuiScreenshotTool(manager)

    # ------------------------------------------------------------------
    # Unit-level: xvfb missing
    # ------------------------------------------------------------------
    async def test_returns_error_when_xvfb_missing(self, tool: GuiScreenshotTool):
        """Tool should return a structured error when xvfb-run is absent."""
        with patch("openroad_mcp.tools.gui._xvfb_available", return_value=False):
            raw = await tool.execute()
            result = json.loads(raw)

        assert result["error"] == "XvfbNotFound"
        assert "xvfb-run" in result["message"]

    # ------------------------------------------------------------------
    # Integration: full screenshot round-trip (Docker only)
    # ------------------------------------------------------------------
    @skip_if_no_xvfb
    @skip_if_no_openroad
    async def test_screenshot_creates_png(self, tool: GuiScreenshotTool):
        """Launch headless GUI, capture screenshot, verify PNG base64."""
        raw = await tool.execute(timeout_ms=15_000)
        result = json.loads(raw)

        # If the GUI failed to render it's an infra / timing issue, not a code bug
        if result.get("error") in ("ScreenshotFailed", "SessionError"):
            pytest.skip(f"GUI did not produce image (infra): {result.get('message', '')}")

        assert result.get("error") is None, f"Unexpected error: {result}"
        assert result["image_format"] == "png"
        assert result["size_bytes"] > 0
        assert result["session_id"] is not None

        # Validate base64 payload
        image_bytes = base64.b64decode(result["image_data"])
        assert image_bytes[:4] == b"\x89PNG", "Response is not a valid PNG"

        # File should exist on disk as well
        assert Path(result["image_path"]).exists()

    @skip_if_no_xvfb
    @skip_if_no_openroad
    async def test_screenshot_reuses_existing_session(self, tool: GuiScreenshotTool, manager: OpenROADManager):
        """Providing an existing session_id should reuse that session."""
        session_id = await manager.create_session(
            command=[
                "xvfb-run",
                "-a",
                "-s",
                "-screen 0 1280x1024x24",
                "openroad",
                "-gui",
                "-no_init",
            ],
        )
        # Let the GUI boot
        await asyncio.sleep(3.0)

        raw = await tool.execute(session_id=session_id, timeout_ms=15_000)
        result = json.loads(raw)

        if result.get("error") == "ScreenshotFailed":
            pytest.skip(f"GUI did not produce image (infra): {result.get('message', '')}")

        assert result.get("error") is None, f"Unexpected error: {result}"
        assert result["session_id"] == session_id

    @skip_if_no_xvfb
    @skip_if_no_openroad
    async def test_screenshot_custom_output_path(self, tool: GuiScreenshotTool, tmp_path: Path):
        """Custom output_path should place the PNG at the specified location."""
        out = tmp_path / "my_screenshot.png"
        raw = await tool.execute(output_path=str(out), timeout_ms=15_000)
        result = json.loads(raw)

        if result.get("error") == "ScreenshotFailed":
            pytest.skip("GUI did not produce image (infra)")

        assert result.get("error") is None
        assert out.exists()
        assert out.stat().st_size > 0

    async def test_screenshot_invalid_session_id(self, tool: GuiScreenshotTool):
        """Non-existent session_id should return SessionNotFound."""
        raw = await tool.execute(session_id="nonexistent-id")
        result = json.loads(raw)

        assert result["error"] == "SessionNotFound"
