"""Unit tests for GuiScreenshotTool implementation.

Tests all code paths using mocked dependencies (no xvfb/OpenROAD required).
Integration tests that exercise the real GUI are in tests/integration/test_gui.py.
"""

import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.core.models import InteractiveExecResult
from openroad_mcp.interactive.models import (
    SessionError,
    SessionNotFoundError,
    SessionTerminatedError,
)
from openroad_mcp.tools.gui import (
    DEFAULT_DISPLAY_RESOLUTION,
    IMAGE_CAPTURE_TIMEOUT_MS,
    MAX_SCREENSHOT_SIZE_MB,
    GuiScreenshotTool,
)

# Minimal valid PNG (1x1 pixel, RGBA)
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
class TestGuiScreenshotTool:
    """Test suite for GuiScreenshotTool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock OpenROADManager."""
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager) -> GuiScreenshotTool:
        """Create GuiScreenshotTool with mock manager."""
        return GuiScreenshotTool(mock_manager)

    # ------------------------------------------------------------------
    # Positive: successful screenshot (happy path)
    # ------------------------------------------------------------------
    async def test_successful_screenshot(self, tool, mock_manager, tmp_path):
        """Full happy path: existing session → save_image → PNG returned."""
        out_file = tmp_path / "screenshot.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="gui-sess-1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )

        # Simulate gui::save_image writing the file during execute_command
        def _write_and_return(*_args, **_kwargs):
            out_file.write_bytes(_MINIMAL_PNG)
            return mock_result

        mock_manager.execute_command.side_effect = _write_and_return

        raw = await tool.execute(session_id="gui-sess-1", output_path=str(out_file))
        result = json.loads(raw)

        assert result["error"] is None
        assert result["session_id"] == "gui-sess-1"
        assert result["image_format"] == "png"
        assert result["size_bytes"] == len(_MINIMAL_PNG)
        assert result["message"] == "Screenshot captured successfully."

        # Verify base64 round-trips correctly
        decoded = base64.b64decode(result["image_data"])
        assert decoded == _MINIMAL_PNG

    async def test_successful_screenshot_auto_session(self, tool, mock_manager, tmp_path):
        """When no session_id is given, a new session is created via xvfb-run."""
        out_file = tmp_path / "auto.png"

        mock_manager.create_session.return_value = "auto-session"

        mock_result = InteractiveExecResult(
            output="",
            session_id="auto-session",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.2,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(out_file, mock_result)

        with patch("openroad_mcp.tools.gui._xvfb_available", return_value=True):
            with patch("asyncio.sleep", new_callable=AsyncMock):  # skip startup delay
                raw = await tool.execute(output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["session_id"] == "auto-session"

        # Verify xvfb-run command was passed to create_session
        call_args = mock_manager.create_session.call_args
        # create_session is called with keyword arg 'command' (a list)
        cmd_list = call_args.kwargs.get("command", call_args.args[0] if call_args.args else [])
        assert "xvfb-run" in cmd_list
        assert "-gui" in cmd_list

    async def test_default_resolution_and_timeout(self, tool, mock_manager, tmp_path):
        """Defaults for resolution and timeout are applied when not specified."""
        out_file = tmp_path / "defaults.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(out_file, mock_result)

        raw = await tool.execute(session_id="s1", output_path=str(out_file))
        result = json.loads(raw)

        assert result["resolution"] == DEFAULT_DISPLAY_RESOLUTION
        # execute_command should receive the default timeout
        call_args = mock_manager.execute_command.call_args.args
        assert call_args[2] == IMAGE_CAPTURE_TIMEOUT_MS

    async def test_custom_resolution(self, tool, mock_manager, tmp_path):
        """Custom resolution is threaded through to the result."""
        out_file = tmp_path / "custom_res.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(
            out_file,
            mock_result,
        )

        raw = await tool.execute(
            session_id="s1",
            resolution="1920x1080x24",
            output_path=str(out_file),
        )
        result = json.loads(raw)

        assert result["resolution"] == "1920x1080x24"

    async def test_custom_timeout(self, tool, mock_manager, tmp_path):
        """Custom timeout_ms is forwarded to execute_command."""
        out_file = tmp_path / "timeout.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(
            out_file,
            mock_result,
        )

        await tool.execute(session_id="s1", output_path=str(out_file), timeout_ms=20_000)

        call_args = mock_manager.execute_command.call_args.args
        assert call_args[2] == 20_000

    # ------------------------------------------------------------------
    # Positive: temp file path generation
    # ------------------------------------------------------------------
    async def test_temp_file_used_when_no_output_path(self, tool, mock_manager):
        """When output_path is omitted a temp file under /tmp is used."""
        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )

        # We need the temp file path to write the PNG into
        written_path: list[Path] = []

        async def _capture_path(sid, cmd, timeout):
            # Extract path from the Tcl command
            # e.g.  gui::save_image "/tmp/openroad_gui_xxxx.png"
            path_str = cmd.split('"')[1]
            p = Path(path_str)
            p.write_bytes(_MINIMAL_PNG)
            written_path.append(p)
            return mock_result

        mock_manager.execute_command.side_effect = _capture_path

        raw = await tool.execute(session_id="s1")
        result = json.loads(raw)

        assert result["error"] is None
        assert result["image_path"].startswith(tempfile.gettempdir())
        assert result["image_path"].endswith(".png")

        # Cleanup
        if written_path:
            written_path[0].unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Negative: xvfb not installed
    # ------------------------------------------------------------------
    async def test_xvfb_not_found_error(self, tool):
        """Returns structured error when xvfb-run is missing."""
        with patch("openroad_mcp.tools.gui._xvfb_available", return_value=False):
            raw = await tool.execute()
            result = json.loads(raw)

        assert result["error"] == "XvfbNotFound"
        assert "xvfb-run" in result["message"]

    # ------------------------------------------------------------------
    # Negative: screenshot file missing / empty
    # ------------------------------------------------------------------
    async def test_screenshot_failed_file_missing(self, tool, mock_manager, tmp_path):
        """Returns ScreenshotFailed when gui::save_image produces no file."""
        out_file = tmp_path / "missing.png"

        mock_result = InteractiveExecResult(
            output="some gui output",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        # Don't write anything — simulate gui::save_image failure
        mock_manager.execute_command.return_value = mock_result

        with patch("openroad_mcp.tools.gui._FILE_POLL_MAX_WAIT", 0.1):  # speed up polling
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)

        assert result["error"] == "ScreenshotFailed"
        assert "not created" in result["message"] or "empty" in result["message"]
        assert result["session_id"] == "s1"

    async def test_screenshot_failed_file_empty(self, tool, mock_manager, tmp_path):
        """Returns ScreenshotFailed when gui::save_image writes a 0-byte file."""
        out_file = tmp_path / "empty.png"

        mock_result = InteractiveExecResult(
            output="gui output",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.return_value = mock_result

        # Write a zero-byte file — simulates partial write
        out_file.write_bytes(b"")

        with patch("openroad_mcp.tools.gui._FILE_POLL_MAX_WAIT", 0.1):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)

        assert result["error"] == "ScreenshotFailed"
        assert result["session_id"] == "s1"

    # ------------------------------------------------------------------
    # Negative: file too large
    # ------------------------------------------------------------------
    async def test_file_too_large_error(self, tool, mock_manager, tmp_path):
        """Returns FileTooLarge when screenshot exceeds MAX_SCREENSHOT_SIZE_MB."""
        out_file = tmp_path / "huge.png"

        # Create a file that exceeds the size limit.
        # The side_effect writes a huge file *during* execute_command,
        # so it exists when the polling loop checks.
        huge_size = (MAX_SCREENSHOT_SIZE_MB + 1) * 1024 * 1024

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )

        def _write_huge(*_a, **_kw):
            out_file.write_bytes(b"\x00" * huge_size)
            return mock_result

        mock_manager.execute_command.side_effect = _write_huge

        raw = await tool.execute(session_id="s1", output_path=str(out_file))
        result = json.loads(raw)

        assert result["error"] == "FileTooLarge"
        assert str(MAX_SCREENSHOT_SIZE_MB) in result["message"]

    # ------------------------------------------------------------------
    # Negative: session not found
    # ------------------------------------------------------------------
    async def test_session_not_found_error(self, tool, mock_manager):
        """Returns SessionNotFound for non-existent session_id."""
        mock_manager.execute_command.side_effect = SessionNotFoundError("not found")

        raw = await tool.execute(session_id="ghost-session")
        result = json.loads(raw)

        assert result["error"] == "SessionNotFound"
        assert result["session_id"] == "ghost-session"
        assert "not found" in result["message"]

    # ------------------------------------------------------------------
    # Negative: session terminated
    # ------------------------------------------------------------------
    async def test_session_terminated_error(self, tool, mock_manager):
        """Returns SessionError when session has terminated."""
        mock_manager.execute_command.side_effect = SessionTerminatedError("session has been terminated")

        raw = await tool.execute(session_id="dead-session")
        result = json.loads(raw)

        assert result["error"] == "SessionError"
        assert result["session_id"] == "dead-session"

    async def test_session_error(self, tool, mock_manager):
        """Returns SessionError for generic session errors."""
        mock_manager.execute_command.side_effect = SessionError("something went wrong")

        raw = await tool.execute(session_id="bad-session")
        result = json.loads(raw)

        assert result["error"] == "SessionError"
        assert "something went wrong" in result["message"]

    # ------------------------------------------------------------------
    # Negative: unexpected exception
    # ------------------------------------------------------------------
    async def test_unexpected_error(self, tool, mock_manager):
        """Returns UnexpectedError for unhandled exceptions."""
        mock_manager.execute_command.side_effect = RuntimeError("kaboom")

        raw = await tool.execute(session_id="s1")
        result = json.loads(raw)

        assert result["error"] == "UnexpectedError"
        assert "kaboom" in result["message"]

    # ------------------------------------------------------------------
    # Edge: stale file is cleaned before screenshot
    # ------------------------------------------------------------------
    async def test_stale_file_removed_before_capture(self, tool, mock_manager, tmp_path):
        """A stale file at the output path is removed before gui::save_image."""
        out_file = tmp_path / "stale.png"
        out_file.write_bytes(b"old data")

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(
            out_file,
            mock_result,
        )

        raw = await tool.execute(session_id="s1", output_path=str(out_file))
        result = json.loads(raw)

        assert result["error"] is None
        # The image_data should be _MINIMAL_PNG, not "old data"
        decoded = base64.b64decode(result["image_data"])
        assert decoded == _MINIMAL_PNG

    # ------------------------------------------------------------------
    # Edge: polling discovers file on a later iteration
    # ------------------------------------------------------------------
    async def test_polling_waits_for_file(self, tool, mock_manager, tmp_path):
        """File appears after a delay — polling loop picks it up."""
        import asyncio

        out_file = tmp_path / "delayed.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.return_value = mock_result

        # Schedule the file to appear after 0.3s
        async def _delayed_write():
            await asyncio.sleep(0.3)
            out_file.write_bytes(_MINIMAL_PNG)

        asyncio.create_task(_delayed_write())

        raw = await tool.execute(session_id="s1", output_path=str(out_file))
        result = json.loads(raw)

        assert result["error"] is None
        assert result["size_bytes"] == len(_MINIMAL_PNG)

    # ------------------------------------------------------------------
    # Result structure: all expected fields present
    # ------------------------------------------------------------------
    async def test_result_contains_all_fields(self, tool, mock_manager, tmp_path):
        """Successful result includes every GuiScreenshotResult field."""
        out_file = tmp_path / "fields.png"

        mock_result = InteractiveExecResult(
            output="",
            session_id="s1",
            timestamp="2024-01-01T00:00:00Z",
            execution_time=0.1,
            command_count=1,
        )
        mock_manager.execute_command.side_effect = lambda *a, **kw: _side_effect_write(
            out_file,
            mock_result,
        )

        raw = await tool.execute(session_id="s1", output_path=str(out_file))
        result = json.loads(raw)

        expected_keys = {
            "session_id",
            "image_data",
            "image_path",
            "image_format",
            "size_bytes",
            "resolution",
            "timestamp",
            "message",
            "error",
        }
        assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"


class TestXvfbAvailability:
    """Tests for the _xvfb_available helper."""

    def test_xvfb_available_when_present(self):
        """Returns True when xvfb-run is on PATH."""
        with patch("openroad_mcp.tools.gui.shutil.which", return_value="/usr/bin/xvfb-run"):
            from openroad_mcp.tools.gui import _xvfb_available

            assert _xvfb_available() is True

    def test_xvfb_available_when_absent(self):
        """Returns False when xvfb-run is not on PATH."""
        with patch("openroad_mcp.tools.gui.shutil.which", return_value=None):
            from openroad_mcp.tools.gui import _xvfb_available

            assert _xvfb_available() is False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _side_effect_write(path: Path, result: InteractiveExecResult) -> InteractiveExecResult:
    """Side effect that writes _MINIMAL_PNG and returns the mock result."""
    path.write_bytes(_MINIMAL_PNG)
    return result
