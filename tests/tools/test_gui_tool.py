"""Unit tests for GuiScreenshotTool implementation.

Tests all code paths using mocked dependencies (no Xvfb/OpenROAD/ImageMagick
required).  Integration tests that exercise the real GUI are in
tests/integration/test_gui.py.
"""

import asyncio
import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openroad_mcp.config.settings import settings
from openroad_mcp.tools.gui import (
    GuiScreenshotTool,
    _find_free_display,
    _wait_for_display,
)

# Minimal valid PNG (1×1 pixel, RGBA)
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # signature
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ------------------------------------------------------------------
# Helpers: mock ``import`` and ``Xvfb`` subprocesses
# ------------------------------------------------------------------


def _make_import_proc(image_path: Path | str | None, *, returncode: int = 0, stderr: bytes = b""):
    """Return a mock that behaves like ``asyncio.create_subprocess_exec``
    created for the ``import`` command.  When *image_path* is not None and
    *returncode* is 0 the mock writes ``_MINIMAL_PNG`` to that path."""
    proc = AsyncMock()
    proc.returncode = returncode

    async def _communicate():
        if returncode == 0 and image_path is not None:
            Path(image_path).write_bytes(_MINIMAL_PNG)
        return b"", stderr

    proc.communicate = _communicate
    proc.kill = MagicMock()
    return proc


def _make_xvfb_proc(*, pid: int = 12345, returncode: int | None = None):
    """Return a mock Xvfb subprocess.  *returncode=None* means still running."""
    proc = AsyncMock()
    proc.pid = pid
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
class TestGuiScreenshotTool:
    """Test suite for GuiScreenshotTool."""

    @pytest.fixture
    def mock_manager(self):
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager) -> GuiScreenshotTool:
        return GuiScreenshotTool(mock_manager)

    # Helper: register a display for an existing session
    def _register_display(self, tool: GuiScreenshotTool, session_id: str, display: int = 42) -> None:
        tool._session_displays[session_id] = display
        tool._xvfb_pids[session_id] = 99999

    # ------------------------------------------------------------------
    # Positive: successful screenshot (happy path, existing session)
    # ------------------------------------------------------------------
    async def test_successful_screenshot(self, tool, tmp_path):
        """Full happy path: existing session → import -window root → PNG."""
        out_file = tmp_path / "screenshot.png"
        self._register_display(tool, "gui-sess-1")

        mock_proc = _make_import_proc(out_file)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="gui-sess-1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["session_id"] == "gui-sess-1"
        assert result["image_format"] == "png"
        assert result["size_bytes"] == len(_MINIMAL_PNG)
        assert result["message"] == "Screenshot captured successfully."
        assert base64.b64decode(result["image_data"]) == _MINIMAL_PNG

    # ------------------------------------------------------------------
    # Positive: auto-session creation (Xvfb + OpenROAD)
    # ------------------------------------------------------------------
    async def test_successful_screenshot_auto_session(self, tool, mock_manager, tmp_path):
        """When no session_id is given, Xvfb + OpenROAD are started."""
        out_file = tmp_path / "auto.png"
        mock_manager.create_session.return_value = "auto-sess"

        xvfb_proc = _make_xvfb_proc()

        # First call → Xvfb, second call → import
        calls = [0]

        async def _create_sub(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                # Xvfb
                return xvfb_proc
            # import
            return _make_import_proc(out_file)

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", side_effect=_create_sub),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("openroad_mcp.tools.gui._wait_for_display", new_callable=AsyncMock, return_value=True),
        ):
            raw = await tool.execute(output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["session_id"] == "auto-sess"

        # Verify create_session used the resolved openroad path
        call_kw = mock_manager.create_session.call_args.kwargs
        cmd = call_kw.get("command", [])
        assert cmd == ["/usr/bin/openroad", "-gui", "-no_init"]
        assert "DISPLAY" in call_kw.get("env", {})

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    async def test_default_resolution_and_timeout(self, tool, tmp_path):
        """Defaults for resolution and timeout are applied."""
        out_file = tmp_path / "defaults.png"
        self._register_display(tool, "s1")

        mock_proc = _make_import_proc(out_file)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["resolution"] == settings.GUI_DISPLAY_RESOLUTION

    async def test_custom_resolution(self, tool, mock_manager, tmp_path):
        """Custom resolution is threaded through to result and Xvfb start."""
        out_file = tmp_path / "res.png"
        mock_manager.create_session.return_value = "res-sess"

        xvfb_proc = _make_xvfb_proc()
        calls = [0]

        async def _create_sub(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                # Xvfb – verify resolution is passed
                assert "1920x1080x24" in args
                return xvfb_proc
            return _make_import_proc(out_file)

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", side_effect=_create_sub),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("openroad_mcp.tools.gui._wait_for_display", new_callable=AsyncMock, return_value=True),
        ):
            raw = await tool.execute(resolution="1920x1080x24", output_path=str(out_file))

        result = json.loads(raw)
        assert result["resolution"] == "1920x1080x24"

    async def test_custom_timeout(self, tool, tmp_path):
        """Custom timeout_ms governs the import subprocess timeout."""
        out_file = tmp_path / "timeout.png"
        self._register_display(tool, "s1")

        mock_proc = _make_import_proc(out_file)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait,
        ):
            await tool.execute(session_id="s1", output_path=str(out_file), timeout_ms=20_000)

        # wait_for should have been called with timeout=20.0
        _, kwargs = mock_wait.call_args
        assert kwargs.get("timeout") == 20.0

    # ------------------------------------------------------------------
    # Positive: temp file path generation
    # ------------------------------------------------------------------
    async def test_temp_file_used_when_no_output_path(self, tool):
        """When output_path is omitted a temp file under /tmp is used."""
        self._register_display(tool, "s1")

        captured_path: list[str] = []

        async def _capture(*args, **kwargs):
            # The 4th positional arg to import is the image path
            path_str = args[3]
            captured_path.append(path_str)
            return _make_import_proc(path_str)

        with patch("asyncio.create_subprocess_exec", side_effect=_capture):
            raw = await tool.execute(session_id="s1")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_path"].startswith(tempfile.gettempdir())
        assert result["image_path"].endswith(".png")

        # Cleanup
        for p in captured_path:
            Path(p).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Negative: pre-flight checks
    # ------------------------------------------------------------------
    async def test_xvfb_not_found_error(self, tool):
        """Returns structured error when Xvfb is missing."""
        with patch("openroad_mcp.tools.gui._xvfb_available", return_value=False):
            raw = await tool.execute()
        result = json.loads(raw)
        assert result["error"] == "XvfbNotFound"
        assert "xvfb" in result["message"].lower()

    async def test_openroad_not_found_error(self, tool):
        """Returns structured error when openroad is missing."""
        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value=None),
        ):
            raw = await tool.execute()
        result = json.loads(raw)
        assert result["error"] == "OpenROADNotFound"
        assert "openroad" in result["message"].lower()

    async def test_import_not_found_error(self, tool):
        """Returns structured error when ImageMagick import is missing."""
        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=False),
        ):
            raw = await tool.execute()
        result = json.loads(raw)
        assert result["error"] == "ImportNotFound"
        assert "imagemagick" in result["message"].lower()

    # ------------------------------------------------------------------
    # Negative: import subprocess failures
    # ------------------------------------------------------------------
    async def test_screenshot_failed_import_error(self, tool, tmp_path):
        """Returns ScreenshotFailed when import exits with non-zero rc."""
        out_file = tmp_path / "fail.png"
        self._register_display(tool, "s1")

        mock_proc = _make_import_proc(None, returncode=1, stderr=b"import: unable to open X server")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] == "ScreenshotFailed"
        assert "rc=1" in result["message"]

    async def test_screenshot_failed_import_timeout(self, tool, tmp_path):
        """Returns ScreenshotFailed when import subprocess times out."""
        out_file = tmp_path / "slow.png"
        self._register_display(tool, "s1")

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()

        async def _hang():
            await asyncio.sleep(999)
            return b"", b""

        mock_proc.communicate = _hang

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), timeout_ms=200)

        result = json.loads(raw)
        assert result["error"] == "ScreenshotFailed"
        assert "timed out" in result["message"].lower()
        mock_proc.kill.assert_called_once()

    async def test_screenshot_failed_file_missing(self, tool, tmp_path):
        """Returns ScreenshotFailed when import exits OK but writes no file."""
        out_file = tmp_path / "missing.png"
        self._register_display(tool, "s1")

        # import succeeds but writes nothing
        mock_proc = _make_import_proc(None, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] == "ScreenshotFailed"
        assert "not created" in result["message"]

    # ------------------------------------------------------------------
    # Negative: file too large
    # ------------------------------------------------------------------
    async def test_file_too_large_error(self, tool, tmp_path):
        """Returns FileTooLarge when screenshot exceeds configured max size."""
        out_file = tmp_path / "huge.png"
        self._register_display(tool, "s1")
        max_mb = settings.GUI_MAX_SCREENSHOT_SIZE_MB
        huge_size = (max_mb + 1) * 1024 * 1024

        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        async def _big():
            out_file.write_bytes(b"\x00" * huge_size)
            return b"", b""

        mock_proc.communicate = _big

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] == "FileTooLarge"
        assert str(max_mb) in result["message"]

    # ------------------------------------------------------------------
    # Negative: session display not registered
    # ------------------------------------------------------------------
    async def test_session_without_display(self, tool):
        """Returns error when session_id has no registered display."""
        raw = await tool.execute(session_id="unknown-sess")
        result = json.loads(raw)
        assert result["error"] == "SessionNotFound"
        assert "no associated X display" in result["message"]

    # ------------------------------------------------------------------
    # Negative: session errors during auto-session creation
    # ------------------------------------------------------------------
    async def test_session_error_on_create(self, tool, mock_manager):
        """Returns SessionError when create_session raises."""
        from openroad_mcp.interactive.models import SessionError as SE

        mock_manager.create_session.side_effect = SE("boom")

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=_make_xvfb_proc()),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("openroad_mcp.tools.gui._wait_for_display", new_callable=AsyncMock, return_value=True),
        ):
            raw = await tool.execute()

        result = json.loads(raw)
        assert result["error"] == "SessionError"
        assert "boom" in result["message"]

    # ------------------------------------------------------------------
    # Negative: unexpected exception
    # ------------------------------------------------------------------
    async def test_unexpected_error(self, tool):
        """Returns UnexpectedError for unhandled exceptions."""
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("kaboom")):
            raw = await tool.execute(session_id="s1")

        result = json.loads(raw)
        assert result["error"] == "UnexpectedError"
        assert "kaboom" in result["message"]

    # ------------------------------------------------------------------
    # Edge: stale file is cleaned before capture
    # ------------------------------------------------------------------
    async def test_stale_file_removed_before_capture(self, tool, tmp_path):
        """A stale file at the output path is removed before import."""
        out_file = tmp_path / "stale.png"
        out_file.write_bytes(b"old data")
        self._register_display(tool, "s1")

        mock_proc = _make_import_proc(out_file)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert base64.b64decode(result["image_data"]) == _MINIMAL_PNG

    # ------------------------------------------------------------------
    # Result structure: all expected fields present
    # ------------------------------------------------------------------
    async def test_result_contains_all_fields(self, tool, tmp_path):
        """Successful result includes every GuiScreenshotResult field."""
        out_file = tmp_path / "fields.png"
        self._register_display(tool, "s1")

        mock_proc = _make_import_proc(out_file)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
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
        assert expected_keys.issubset(result.keys()), f"Missing: {expected_keys - result.keys()}"

    # ------------------------------------------------------------------
    # Xvfb start failure
    # ------------------------------------------------------------------
    async def test_xvfb_start_failed(self, tool):
        """Returns error when Xvfb exits immediately."""
        xvfb_proc = _make_xvfb_proc(returncode=1)  # exited immediately

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=xvfb_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            raw = await tool.execute()

        result = json.loads(raw)
        assert result["error"] == "XvfbStartFailed"

    # ------------------------------------------------------------------
    # cleanup_display helper
    # ------------------------------------------------------------------
    async def test_cleanup_display_kills_xvfb(self, tool):
        """cleanup_display sends SIGTERM to the stored Xvfb PID."""
        tool._session_displays["s1"] = 42
        tool._xvfb_pids["s1"] = 12345

        with patch("os.kill") as mock_kill:
            tool.cleanup_display("s1")

        mock_kill.assert_called_once()
        assert "s1" not in tool._session_displays
        assert "s1" not in tool._xvfb_pids

    async def test_cleanup_display_noop_for_unknown(self, tool):
        """cleanup_display is a safe no-op for unknown session ids."""
        tool.cleanup_display("nonexistent")  # should not raise


# ------------------------------------------------------------------
# Standalone helper tests
# ------------------------------------------------------------------


class TestPreFlightHelpers:
    """Tests for module-level pre-flight helpers."""

    def test_xvfb_available_when_present(self):
        with patch("openroad_mcp.tools.gui.shutil.which", return_value="/usr/bin/Xvfb"):
            from openroad_mcp.tools.gui import _xvfb_available

            assert _xvfb_available() is True

    def test_xvfb_available_when_absent(self):
        with patch("openroad_mcp.tools.gui.shutil.which", return_value=None):
            from openroad_mcp.tools.gui import _xvfb_available

            assert _xvfb_available() is False

    def test_import_available_when_present(self):
        with patch("openroad_mcp.tools.gui.shutil.which", return_value="/usr/bin/import"):
            from openroad_mcp.tools.gui import _import_available

            assert _import_available() is True

    def test_import_available_when_absent(self):
        with patch("openroad_mcp.tools.gui.shutil.which", return_value=None):
            from openroad_mcp.tools.gui import _import_available

            assert _import_available() is False

    def test_find_free_display_no_locks(self, tmp_path):
        """Returns first number in configured range when no lock files exist."""
        with patch("openroad_mcp.tools.gui.Path") as MockPath:
            MockPath.return_value.exists.return_value = False
            num = _find_free_display()
            assert settings.GUI_DISPLAY_START <= num < settings.GUI_DISPLAY_START + 200

    def test_get_openroad_exe_from_env(self, tmp_path):
        """OPENROAD_EXE env var is preferred over PATH lookup."""
        fake_bin = tmp_path / "openroad"
        fake_bin.write_text("#!/bin/sh\n")
        fake_bin.chmod(0o755)

        from openroad_mcp.tools.gui import _get_openroad_exe

        with patch.dict("os.environ", {"OPENROAD_EXE": str(fake_bin)}):
            result = _get_openroad_exe()
        assert result == str(fake_bin.resolve())

    def test_get_openroad_exe_falls_back_to_which(self):
        """Falls back to shutil.which when OPENROAD_EXE is not set."""
        from openroad_mcp.tools.gui import _get_openroad_exe

        with (
            patch.dict("os.environ", {}, clear=False),
            patch("openroad_mcp.tools.gui.os.environ.get", return_value=None),
            patch("openroad_mcp.tools.gui.shutil.which", return_value="/usr/bin/openroad"),
        ):
            result = _get_openroad_exe()
        assert result == "/usr/bin/openroad"

    def test_get_openroad_exe_returns_none(self):
        """Returns None when openroad is not found anywhere."""
        from openroad_mcp.tools.gui import _get_openroad_exe

        with (
            patch.dict("os.environ", {"OPENROAD_EXE": "/nonexistent/openroad"}),
            patch("openroad_mcp.tools.gui.shutil.which", return_value=None),
        ):
            result = _get_openroad_exe()
        assert result is None


@pytest.mark.asyncio
class TestWaitForDisplay:
    """Tests for the _wait_for_display readiness polling helper."""

    async def test_display_ready_immediately(self):
        """Returns True when xdpyinfo succeeds on the first poll."""
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=0)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_display(42)

        assert result is True

    async def test_display_ready_after_retries(self):
        """Returns True when xdpyinfo fails initially then succeeds."""
        call_count = [0]

        async def _make_proc(*args, **kwargs):
            call_count[0] += 1
            proc = AsyncMock()
            # Succeed on 3rd attempt
            proc.wait = AsyncMock(return_value=0 if call_count[0] >= 3 else 1)
            return proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_make_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_display(50)

        assert result is True
        assert call_count[0] >= 3

    async def test_display_timeout(self):
        """Returns False when display never becomes ready within timeout."""
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=1)  # always fail

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "GUI_STARTUP_TIMEOUT_S", 1.0),
            patch.object(settings, "GUI_STARTUP_POLL_INTERVAL_S", 0.5),
        ):
            result = await _wait_for_display(99)

        assert result is False

    async def test_display_handles_oserror(self):
        """Continues polling if xdpyinfo raises OSError (e.g. not installed)."""
        call_count = [0]

        async def _make_proc(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise OSError("No such file")
            proc = AsyncMock()
            proc.wait = AsyncMock(return_value=0)
            return proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_make_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_display(42)

        assert result is True
