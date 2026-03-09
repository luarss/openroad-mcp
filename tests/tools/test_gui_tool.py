"""Unit tests for GuiScreenshotTool implementation.

Tests all code paths using mocked dependencies (no Xvfb/OpenROAD/ImageMagick
required).  Integration tests that exercise the real GUI are in
tests/integration/test_gui.py.
"""

import asyncio
import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image as PILImage

from openroad_mcp.config.settings import settings
from openroad_mcp.tools.gui import (
    GuiScreenshotTool,
    _find_free_display,
    _wait_for_display,
    _wait_for_gui_ready,
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
    proc.terminate = MagicMock()
    return proc


def _make_import_side_effect(
    *,
    returncode: int = 0,
    stderr: bytes = b"",
    png_data: bytes | None = None,
):
    """Return an async callable for ``side_effect`` of
    ``asyncio.create_subprocess_exec`` that mimics ImageMagick ``import``.

    Unlike ``_make_import_proc`` this dynamically captures the output-path
    from the call arguments (``import -window root <path>``) so the test
    does not need to know the internal raw-path name.

    When *png_data* is given it is written instead of ``_MINIMAL_PNG``.
    """
    data = png_data if png_data is not None else _MINIMAL_PNG

    async def _factory(*args, **kwargs):
        proc = AsyncMock()
        proc.returncode = returncode
        proc.kill = MagicMock()
        # ``import -window root <path>``  →  args[3] is the path
        img_path = args[3] if len(args) > 3 else None

        async def _communicate():
            if returncode == 0 and img_path is not None:
                Path(img_path).write_bytes(data)
            return b"", stderr

        proc.communicate = _communicate
        return proc

    return _factory


def _create_test_png(width: int = 100, height: int = 80) -> bytes:
    """Create a solid-colour PNG of the given dimensions using Pillow."""
    img = PILImage.new("RGBA", (width, height), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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
        """Full happy path: existing session → import → JPEG (default)."""
        out_file = tmp_path / "screenshot.jpg"
        self._register_display(tool, "gui-sess-1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="gui-sess-1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["session_id"] == "gui-sess-1"
        assert result["image_format"] == "jpeg"  # default
        assert result["size_bytes"] > 0
        assert result["original_size_bytes"] > 0
        assert result["compression_applied"] is True
        assert result["return_mode"] == "base64"
        assert result["width"] == 1
        assert result["height"] == 1
        assert result["message"] == "Screenshot captured successfully."
        # Verify base64 data decodes to valid image bytes
        img_bytes = base64.b64decode(result["image_data"])
        assert len(img_bytes) > 0

    # ------------------------------------------------------------------
    # Positive: auto-session creation (Xvfb + OpenROAD)
    # ------------------------------------------------------------------
    async def test_successful_screenshot_auto_session(self, tool, mock_manager, tmp_path):
        """When no session_id is given, Xvfb + OpenROAD are started."""
        out_file = tmp_path / "auto.jpg"
        mock_manager.create_session.return_value = "auto-sess"

        xvfb_proc = _make_xvfb_proc()
        import_factory = _make_import_side_effect()

        # First call → Xvfb, subsequent calls → import
        calls = [0]

        async def _create_sub(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                return xvfb_proc
            return await import_factory(*args, **kwargs)

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", side_effect=_create_sub),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("openroad_mcp.tools.gui._wait_for_display", new_callable=AsyncMock, return_value=True),
            patch("openroad_mcp.tools.gui._wait_for_gui_ready", new_callable=AsyncMock, return_value=True),
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
        out_file = tmp_path / "defaults.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["resolution"] == settings.GUI_DISPLAY_RESOLUTION

    async def test_custom_resolution(self, tool, mock_manager, tmp_path):
        """Custom resolution is threaded through to result and Xvfb start."""
        out_file = tmp_path / "res.jpg"
        mock_manager.create_session.return_value = "res-sess"

        xvfb_proc = _make_xvfb_proc()
        import_factory = _make_import_side_effect()
        calls = [0]

        async def _create_sub(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                # Xvfb – verify resolution is passed
                assert "1920x1080x24" in args
                return xvfb_proc
            return await import_factory(*args, **kwargs)

        with (
            patch("openroad_mcp.tools.gui._xvfb_available", return_value=True),
            patch("openroad_mcp.tools.gui._get_openroad_exe", return_value="/usr/bin/openroad"),
            patch("openroad_mcp.tools.gui._import_available", return_value=True),
            patch("asyncio.create_subprocess_exec", side_effect=_create_sub),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("openroad_mcp.tools.gui._wait_for_display", new_callable=AsyncMock, return_value=True),
            patch("openroad_mcp.tools.gui._wait_for_gui_ready", new_callable=AsyncMock, return_value=True),
        ):
            raw = await tool.execute(resolution="1920x1080x24", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
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

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_path"].startswith(tempfile.gettempdir())
        assert result["image_path"].endswith(".jpg")  # default JPEG

        # Cleanup
        Path(result["image_path"]).unlink(missing_ok=True)

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
        """Returns FileTooLarge when processed screenshot exceeds max size."""
        out_file = tmp_path / "huge.jpg"
        self._register_display(tool, "s1")

        # Set max to 0 so any image exceeds the limit
        with (
            patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()),
            patch.object(settings, "GUI_MAX_SCREENSHOT_SIZE_MB", 0),
        ):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] == "FileTooLarge"
        assert "exceeds" in result["message"].lower()

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
            patch("openroad_mcp.tools.gui._wait_for_gui_ready", new_callable=AsyncMock, return_value=True),
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
    async def test_stale_file_overwritten(self, tool, tmp_path):
        """A stale file at the output path is overwritten with the new image."""
        out_file = tmp_path / "stale.jpg"
        out_file.write_bytes(b"old data")
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        # File should contain new image, not old data
        assert out_file.read_bytes() != b"old data"
        assert result["size_bytes"] > 0

    # ------------------------------------------------------------------
    # Result structure: all expected fields present
    # ------------------------------------------------------------------
    async def test_result_contains_all_fields(self, tool, tmp_path):
        """Successful result includes every GuiScreenshotResult field."""
        out_file = tmp_path / "fields.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        expected_keys = {
            "session_id",
            "image_data",
            "image_path",
            "image_format",
            "size_bytes",
            "original_size_bytes",
            "resolution",
            "timestamp",
            "message",
            "error",
            "return_mode",
            "compression_applied",
            "compression_ratio",
            "width",
            "height",
        }
        assert expected_keys.issubset(result.keys()), f"Missing: {expected_keys - result.keys()}"

    # ------------------------------------------------------------------
    # Image format tests
    # ------------------------------------------------------------------
    async def test_explicit_png_format(self, tool, tmp_path):
        """Explicit image_format='png' produces a PNG."""
        out_file = tmp_path / "shot.png"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), image_format="png")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "png"
        # PNG signature: starts with \x89PNG
        img_bytes = base64.b64decode(result["image_data"])
        assert img_bytes[:4] == b"\x89PNG"

    async def test_webp_format(self, tool, tmp_path):
        """image_format='webp' produces a WebP file."""
        out_file = tmp_path / "shot.webp"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), image_format="webp")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "webp"
        # WebP signature: starts with RIFF....WEBP
        img_bytes = base64.b64decode(result["image_data"])
        assert img_bytes[:4] == b"RIFF"
        assert img_bytes[8:12] == b"WEBP"

    async def test_jpeg_default_format(self, tool, tmp_path):
        """Default format is JPEG; RGBA PNG gets converted to RGB."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "jpeg"
        # JPEG signature: starts with FF D8 FF
        img_bytes = base64.b64decode(result["image_data"])
        assert img_bytes[:2] == b"\xff\xd8"

    # ------------------------------------------------------------------
    # Quality tests
    # ------------------------------------------------------------------
    async def test_jpeg_quality_low(self, tool, tmp_path):
        """Low quality JPEG produces a smaller file than high quality."""
        self._register_display(tool, "s1")

        # Use a larger PNG so quality difference is measurable
        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw_low = await tool.execute(
                session_id="s1",
                output_path=str(tmp_path / "low.jpg"),
                quality=10,
            )

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw_high = await tool.execute(
                session_id="s1",
                output_path=str(tmp_path / "high.jpg"),
                quality=95,
            )

        low = json.loads(raw_low)
        high = json.loads(raw_high)
        assert low["error"] is None
        assert high["error"] is None
        assert low["size_bytes"] < high["size_bytes"]

    # ------------------------------------------------------------------
    # Scale tests
    # ------------------------------------------------------------------
    async def test_scale_downscale(self, tool, tmp_path):
        """scale=0.5 halves the image dimensions."""
        out_file = tmp_path / "scaled.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                scale=0.5,
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["width"] == 50
        assert result["height"] == 40
        assert result["compression_applied"] is True

    async def test_scale_one_no_resize(self, tool, tmp_path):
        """scale=1.0 (default) preserves original dimensions."""
        out_file = tmp_path / "noscale.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                scale=1.0,
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["width"] == 100
        assert result["height"] == 80

    # ------------------------------------------------------------------
    # Crop tests
    # ------------------------------------------------------------------
    async def test_crop_region(self, tool, tmp_path):
        """Cropping extracts a subregion of the image."""
        out_file = tmp_path / "cropped.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                crop="10 10 60 50",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["width"] == 50  # 60 - 10
        assert result["height"] == 40  # 50 - 10
        assert result["compression_applied"] is True

    async def test_crop_then_scale(self, tool, tmp_path):
        """Crop is applied before scale: crop first, then resize."""
        out_file = tmp_path / "crop_scale.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                crop="0 0 100 80",
                scale=0.5,
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["width"] == 50
        assert result["height"] == 40

    async def test_crop_invalid_format(self, tool, tmp_path):
        """Invalid crop string returns InvalidParameter error."""
        out_file = tmp_path / "bad_crop.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                crop="not numbers",
            )

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "crop" in result["message"].lower()

    async def test_crop_wrong_count(self, tool, tmp_path):
        """Crop with wrong number of coordinates returns error."""
        out_file = tmp_path / "bad_crop2.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                crop="10 20 30",
            )

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "4" in result["message"]

    # ------------------------------------------------------------------
    # Return mode tests
    # ------------------------------------------------------------------
    async def test_return_mode_path(self, tool, tmp_path):
        """return_mode='path' omits image_data for token savings."""
        out_file = tmp_path / "path_only.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                return_mode="path",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "path"
        assert result["image_data"] is None
        assert result["image_path"] == str(out_file)
        assert result["size_bytes"] > 0
        assert "saved to" in result["message"].lower()

    async def test_return_mode_preview(self, tool, tmp_path):
        """return_mode='preview' returns a small thumbnail and the full path."""
        out_file = tmp_path / "preview.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                return_mode="preview",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "preview"
        assert result["image_data"] is not None
        assert result["image_path"] == str(out_file)
        assert "preview" in result["message"].lower() or "thumbnail" in result["message"].lower()

        # Preview image should be smaller than or equal to 256px on longest side
        preview_bytes = base64.b64decode(result["image_data"])
        preview_img = PILImage.open(io.BytesIO(preview_bytes))
        assert max(preview_img.size) <= 256
        # Result metadata must reflect the thumbnail, not the full image
        assert result["width"] == preview_img.size[0]
        assert result["height"] == preview_img.size[1]
        assert result["size_bytes"] == len(preview_bytes)
        preview_img.close()

        # File on disk must also be the thumbnail, not the full-size image
        disk_img = PILImage.open(out_file)
        assert max(disk_img.size) <= 256
        assert disk_img.size == (result["width"], result["height"])
        disk_img.close()

    async def test_return_mode_base64_default(self, tool, tmp_path):
        """Default return_mode is 'base64' with full image data."""
        out_file = tmp_path / "base64.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "base64"
        assert result["image_data"] is not None
        assert result["image_path"] == str(out_file)

    # ------------------------------------------------------------------
    # Parameter validation tests
    # ------------------------------------------------------------------
    async def test_invalid_format_error(self, tool):
        """Unsupported image format returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", image_format="bmp")

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "bmp" in result["message"]
        assert "jpeg" in result["message"]

    async def test_invalid_return_mode_error(self, tool):
        """Unsupported return_mode returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", return_mode="inline")

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "inline" in result["message"]
        assert "base64" in result["message"]

    async def test_invalid_scale_zero(self, tool):
        """scale=0 returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", scale=0.0)

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "scale" in result["message"].lower()

    async def test_invalid_scale_negative(self, tool):
        """Negative scale returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", scale=-0.5)

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "scale" in result["message"].lower()

    async def test_invalid_scale_over_one(self, tool):
        """scale > 1.0 returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", scale=1.5)

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "scale" in result["message"].lower()

    async def test_invalid_quality_zero(self, tool):
        """quality=0 returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", quality=0)

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "quality" in result["message"].lower()

    async def test_invalid_quality_over_100(self, tool):
        """quality=101 returns InvalidParameter."""
        self._register_display(tool, "s1")

        raw = await tool.execute(session_id="s1", quality=101)

        result = json.loads(raw)
        assert result["error"] == "InvalidParameter"
        assert "quality" in result["message"].lower()

    # ------------------------------------------------------------------
    # Compression ratio field
    # ------------------------------------------------------------------
    async def test_compression_ratio_jpeg(self, tool, tmp_path):
        """JPEG compression reports a non-None compression_ratio."""
        out_file = tmp_path / "ratio.jpg"
        self._register_display(tool, "s1")

        big_png = _create_test_png(100, 80)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=_make_import_side_effect(png_data=big_png),
        ):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["compression_applied"] is True
        assert result["compression_ratio"] is not None
        assert 0 < result["compression_ratio"]  # ratio > 0
        assert result["original_size_bytes"] > 0

    async def test_no_compression_png(self, tool, tmp_path):
        """PNG at scale=1.0 with no crop reports compression_applied=False."""
        out_file = tmp_path / "plain.png"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                image_format="png",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["compression_applied"] is False
        assert result["compression_ratio"] is None

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
    # Empty-string normalisation (MCP Inspector sends "" for blank fields)
    # ------------------------------------------------------------------
    async def test_empty_string_image_format_uses_default(self, tool, tmp_path):
        """Empty string for image_format should use default (jpeg), not error."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), image_format="")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "jpeg"  # default, not error

    async def test_empty_string_return_mode_uses_default(self, tool, tmp_path):
        """Empty string for return_mode should default to 'base64'."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), return_mode="")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "base64"

    async def test_empty_string_resolution_uses_default(self, tool, tmp_path):
        """Empty string for resolution should use default, not error."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), resolution="")

        result = json.loads(raw)
        assert result["error"] is None
        # Should use default resolution, not error
        assert result["resolution"] == settings.GUI_DISPLAY_RESOLUTION

    async def test_empty_string_crop_ignored(self, tool, tmp_path):
        """Empty string for crop should be treated as no crop."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), crop="")

        result = json.loads(raw)
        assert result["error"] is None

    # ------------------------------------------------------------------
    # output_path: parent directory creation & extension correction
    # ------------------------------------------------------------------
    async def test_output_path_creates_parent_dirs(self, tool, tmp_path):
        """output_path with non-existent parent directory should create it."""
        nested_dir = tmp_path / "deep" / "nested" / "dir"
        out_file = nested_dir / "screenshot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert nested_dir.exists()
        assert Path(result["image_path"]).exists()

    async def test_output_path_extension_corrected_for_format(self, tool, tmp_path):
        """output_path with wrong extension gets corrected to match image_format."""
        out_file = tmp_path / "screenshot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                image_format="png",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "png"
        # Extension should be corrected to .png
        assert result["image_path"].endswith(".png")

    async def test_output_path_correct_extension_preserved(self, tool, tmp_path):
        """output_path with correct extension is preserved as-is."""
        out_file = tmp_path / "screenshot.png"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(
                session_id="s1",
                output_path=str(out_file),
                image_format="png",
            )

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_path"] == str(out_file)

    async def test_explicit_png_format_with_empty_string_output(self, tool):
        """image_format='png' with output_path='' uses temp file with .png ext."""
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path="", image_format="png")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "png"
        assert result["image_path"].endswith(".png")

    async def test_format_inferred_from_output_path_extension(self, tool, tmp_path):
        """When image_format is omitted, format is inferred from output_path ext."""
        out_file = tmp_path / "my_screenshot.png"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file))

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "png"
        assert result["image_path"] == str(out_file)
        assert out_file.exists()

    # ------------------------------------------------------------------
    # Whitespace stripping (MCP Inspector may pad string values)
    # ------------------------------------------------------------------
    async def test_whitespace_padded_image_format(self, tool, tmp_path):
        """Whitespace around image_format should be stripped."""
        out_file = tmp_path / "shot.png"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), image_format="  png  ")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["image_format"] == "png"

    async def test_whitespace_padded_return_mode(self, tool, tmp_path):
        """Whitespace around return_mode should be stripped."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), return_mode="  path  ")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "path"
        assert result["image_data"] is None

    # ------------------------------------------------------------------
    # Crop: comma separators and numeric input
    # ------------------------------------------------------------------
    async def test_crop_with_commas(self, tool, tmp_path):
        """Comma-separated crop values should be accepted."""
        out_file = tmp_path / "cropped.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), crop="10,10,50,50")

        result = json.loads(raw)
        assert result["error"] is None

    async def test_crop_with_mixed_separators(self, tool, tmp_path):
        """Crop values with mixed commas and spaces should be accepted."""
        out_file = tmp_path / "cropped.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), crop="10, 10, 50, 50")

        result = json.loads(raw)
        assert result["error"] is None

    # ------------------------------------------------------------------
    # Extension validation: .jpeg recognised for jpeg format
    # ------------------------------------------------------------------
    async def test_jpeg_extension_preserved(self, tool, tmp_path):
        """.jpeg extension should be accepted for jpeg format."""
        out_file = tmp_path / "shot.jpeg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), image_format="jpeg")

        result = json.loads(raw)
        assert result["error"] is None
        # .jpeg should be preserved, not changed to .jpg
        assert result["image_path"] == str(out_file)

    # ------------------------------------------------------------------
    # return_mode=path: no image data, only file path
    # ------------------------------------------------------------------
    async def test_return_mode_path_omits_image_data(self, tool, tmp_path):
        """return_mode='path' should omit image_data."""
        out_file = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_file), return_mode="path")

        result = json.loads(raw)
        assert result["error"] is None
        assert result["return_mode"] == "path"
        assert result["image_data"] is None
        assert result["image_path"] is not None

    # ------------------------------------------------------------------
    # output_path as existing directory
    # ------------------------------------------------------------------
    async def test_output_path_existing_directory_generates_file_inside(self, tool, tmp_path):
        """When output_path is an existing directory, generate a default filename inside it."""
        out_dir = tmp_path / "screenshots"
        out_dir.mkdir()
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_dir))

        result = json.loads(raw)
        assert result["error"] is None
        # The image should be inside the directory, not at the directory path itself
        final = Path(result["image_path"])
        assert final.parent == out_dir
        assert final.name.startswith("openroad_gui_")
        assert final.exists()

    async def test_output_path_trailing_slash_treated_as_directory(self, tool, tmp_path):
        """output_path ending with '/' should be treated as a directory."""
        out_dir = tmp_path / "output"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_dir) + "/")

        result = json.loads(raw)
        assert result["error"] is None
        final = Path(result["image_path"])
        assert final.parent == out_dir
        assert final.name.startswith("openroad_gui_")
        assert final.exists()

    async def test_output_path_directory_respects_format(self, tool, tmp_path):
        """Directory output_path should generate file with correct format extension."""
        out_dir = tmp_path / "pngs"
        out_dir.mkdir()
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out_dir), image_format="png")

        result = json.loads(raw)
        assert result["error"] is None
        final = Path(result["image_path"])
        assert final.suffix == ".png"

    # ------------------------------------------------------------------
    # Numeric params: empty/None resets to default
    # ------------------------------------------------------------------
    async def test_scale_none_resets_to_default(self, tool, tmp_path):
        """scale=None should reset to 1.0 (no scaling), not retain previous value."""
        out = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")
        big_png = _create_test_png(100, 80)

        # First call with scale=0.5
        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect(png_data=big_png)):
            raw1 = await tool.execute(session_id="s1", output_path=str(out), scale=0.5)
        r1 = json.loads(raw1)
        assert r1["error"] is None
        assert r1["width"] == 50

        # Second call without scale (None → default 1.0)
        out2 = tmp_path / "shot2.jpg"
        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect(png_data=big_png)):
            raw2 = await tool.execute(session_id="s1", output_path=str(out2), scale=None)
        r2 = json.loads(raw2)
        assert r2["error"] is None
        # Full-size image should be original dimensions
        assert r2["width"] == 100

    async def test_quality_none_uses_default(self, tool, tmp_path):
        """quality=None should use the default quality setting."""
        out = tmp_path / "shot.jpg"
        self._register_display(tool, "s1")

        with patch("asyncio.create_subprocess_exec", side_effect=_make_import_side_effect()):
            raw = await tool.execute(session_id="s1", output_path=str(out), quality=None)

        result = json.loads(raw)
        assert result["error"] is None


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

    def test_find_free_display_no_locks(self):
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


@pytest.mark.asyncio
class TestWaitForGuiReady:
    """Tests for the _wait_for_gui_ready window-detection helper."""

    def _make_xwininfo_proc(self, stdout_text: str, *, returncode: int = 0):
        """Build a mock subprocess for xwininfo that returns *stdout_text*."""
        proc = AsyncMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout_text.encode("utf-8"), b""))
        return proc

    # Example xwininfo output with no children (just root)
    _NO_CHILDREN = """\
xwininfo: Window id: 0x3e (the root window) "root"

  Root window id: 0x3e (the root window) "root"
  Parent window id: 0x0 (none)
     0 children.
"""

    # Example xwininfo output with OpenROAD window present
    _HAS_CHILDREN = """\
xwininfo: Window id: 0x3e (the root window) "root"

  Root window id: 0x3e (the root window) "root"
  Parent window id: 0x0 (none)
     1 child:
     0x1400001 (has no name): ("openroad" "OpenROAD")  1280x1024+0+0  +0+0
"""

    async def test_gui_ready_immediately(self):
        """Returns True when a child window is found on the first poll."""
        proc = self._make_xwininfo_proc(self._HAS_CHILDREN)

        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_gui_ready(42)

        assert result is True

    async def test_gui_ready_after_retries(self):
        """Returns True when children appear after a few polls."""
        call_count = [0]

        async def _make_proc(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                return self._make_xwininfo_proc(self._NO_CHILDREN)
            return self._make_xwininfo_proc(self._HAS_CHILDREN)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_make_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_gui_ready(50)

        assert result is True
        assert call_count[0] >= 3

    async def test_gui_ready_timeout(self):
        """Returns False when no child window appears within timeout."""
        proc = self._make_xwininfo_proc(self._NO_CHILDREN)

        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(settings, "GUI_APP_READY_TIMEOUT_S", 1.0),
            patch.object(settings, "GUI_APP_READY_POLL_INTERVAL_S", 0.5),
        ):
            result = await _wait_for_gui_ready(99)

        assert result is False

    async def test_gui_ready_handles_oserror(self):
        """Continues polling when xwininfo raises OSError."""
        call_count = [0]

        async def _make_proc(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise OSError("No such file")
            return self._make_xwininfo_proc(self._HAS_CHILDREN)

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_make_proc),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _wait_for_gui_ready(42)

        assert result is True
