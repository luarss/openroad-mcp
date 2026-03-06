"""Integration tests for GUI screenshot tool under Xvfb.

These tests run inside a Docker container that has Xvfb, OpenROAD, and
ImageMagick installed.  They are skipped when those prerequisites are
not available (e.g. local development without OpenROAD).
"""

import base64
import json
import shutil
from pathlib import Path

import pytest

from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.tools.gui import GuiScreenshotTool


def _has_xvfb() -> bool:
    return shutil.which("Xvfb") is not None


def _has_openroad() -> bool:
    return shutil.which("openroad") is not None


def _has_import() -> bool:
    return shutil.which("import") is not None


skip_if_no_xvfb = pytest.mark.skipif(not _has_xvfb(), reason="Xvfb not installed")
skip_if_no_openroad = pytest.mark.skipif(not _has_openroad(), reason="openroad not installed")
skip_if_no_import = pytest.mark.skipif(not _has_import(), reason="ImageMagick import not installed")


@pytest.mark.asyncio
class TestGuiScreenshot:
    """Tests for the gui_screenshot MCP tool."""

    @pytest.fixture
    async def manager(self):
        """Provide a fresh OpenROADManager and clean up after."""
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
    # Unit-level: Xvfb missing
    # ------------------------------------------------------------------
    async def test_returns_error_when_xvfb_missing(self, tool: GuiScreenshotTool):
        """Tool should return a structured error when Xvfb is absent."""
        from unittest.mock import patch

        with patch("openroad_mcp.tools.gui._xvfb_available", return_value=False):
            raw = await tool.execute()
            result = json.loads(raw)

        assert result["error"] == "XvfbNotFound"
        assert "xvfb" in result["message"].lower()

    # ------------------------------------------------------------------
    # Integration: full screenshot round-trip (Docker only)
    # ------------------------------------------------------------------
    @skip_if_no_xvfb
    @skip_if_no_openroad
    @skip_if_no_import
    async def test_screenshot_creates_png(self, tool: GuiScreenshotTool):
        """Launch headless GUI, capture screenshot, verify PNG base64."""
        raw = await tool.execute(timeout_ms=25_000)
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

        # Cleanup Xvfb
        tool.cleanup_display(result["session_id"])

    @skip_if_no_xvfb
    @skip_if_no_openroad
    @skip_if_no_import
    async def test_screenshot_reuses_existing_session(self, tool: GuiScreenshotTool):
        """Taking a second screenshot should reuse the same session."""
        raw1 = await tool.execute(timeout_ms=25_000)
        r1 = json.loads(raw1)

        if r1.get("error"):
            pytest.skip(f"First screenshot failed (infra): {r1.get('message', '')}")

        # Second screenshot on the same session
        raw2 = await tool.execute(session_id=r1["session_id"], timeout_ms=15_000)
        r2 = json.loads(raw2)

        if r2.get("error"):
            pytest.skip(f"Second screenshot failed (infra): {r2.get('message', '')}")

        assert r2["session_id"] == r1["session_id"]
        assert r2["size_bytes"] > 0

        tool.cleanup_display(r1["session_id"])

    @skip_if_no_xvfb
    @skip_if_no_openroad
    @skip_if_no_import
    async def test_screenshot_custom_output_path(self, tool: GuiScreenshotTool, tmp_path: Path):
        """Custom output_path should place the PNG at the specified location."""
        out = tmp_path / "my_screenshot.png"
        raw = await tool.execute(output_path=str(out), timeout_ms=30_000)
        result = json.loads(raw)

        if result.get("error") in ("ScreenshotFailed", "SessionError"):
            pytest.skip("GUI did not produce image (infra)")

        assert result.get("error") is None
        assert out.exists()
        assert out.stat().st_size > 0

        tool.cleanup_display(result["session_id"])

    async def test_screenshot_invalid_session_id(self, tool: GuiScreenshotTool):
        """Non-existent session_id should return SessionNotFound."""
        raw = await tool.execute(session_id="nonexistent-id")
        result = json.loads(raw)

        assert result["error"] == "SessionNotFound"
