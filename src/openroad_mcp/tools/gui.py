"""GUI screenshot tool for headless OpenROAD GUI sessions.

Strategy
--------
OpenROAD in ``-gui`` mode does **not** read Tcl commands from stdin /
the PTY.  The Tcl console is a Qt widget whose I/O is internal to the
application.  This means the PTY-based ``execute_command`` path cannot
be used to call ``gui::save_image``.

Instead we capture what the virtual framebuffer is showing by using
ImageMagick's ``import -window root`` command, which grabs the X11
root window.  This reliably produces a PNG of the full GUI regardless
of whether a design is loaded.

The lifecycle is:

1. Start **Xvfb** on a deterministic display number.
2. Launch ``openroad -gui -no_init`` via the session manager with
   ``DISPLAY`` pointed at that Xvfb instance.
3. Poll the display with ``xdpyinfo`` until a window appears (with a
   configurable timeout fallback).
4. Run ``import -window root <path>`` on the same ``DISPLAY``.
5. Post-process the raw PNG (crop, scale, format conversion) using
   Pillow, then return based on the requested ``return_mode``.
"""

import asyncio
import base64
import io
import os
import shutil
import signal
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

from ..config.settings import settings
from ..core.manager import OpenROADManager
from ..core.models import GuiScreenshotResult
from ..interactive.models import SessionError, SessionNotFoundError, SessionTerminatedError
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("gui_tools")

# ---------------------------------------------------------------------------
# Derived constants – computed once from centralised settings.
# Module-level names kept for backward compatibility and test imports.
# ---------------------------------------------------------------------------

MAX_SCREENSHOT_SIZE_MB: int = settings.GUI_MAX_SCREENSHOT_SIZE_MB

# Accepted image output formats
_VALID_FORMATS = {"png", "jpeg", "webp"}

# Accepted return modes
_VALID_RETURN_MODES = {"base64", "path", "preview"}

# Preview thumbnail max dimension (longest side)
_PREVIEW_SIZE = 256


# ---------------------------------------------------------------------------
# Pre-flight helpers
# ---------------------------------------------------------------------------


def _xvfb_available() -> bool:
    """Check whether Xvfb is on PATH."""
    return shutil.which("Xvfb") is not None


def _get_openroad_exe() -> str | None:
    """Resolve the OpenROAD executable path.

    Checks (in order):
    1. ``OPENROAD_EXE`` environment variable (used by OpenROAD-flow-scripts)
    2. ``shutil.which("openroad")`` (standard PATH lookup)

    Returns the absolute path string or *None* if not found.
    """
    env_exe = os.environ.get("OPENROAD_EXE")
    if env_exe:
        p = Path(env_exe)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p.resolve())
    found = shutil.which("openroad")
    return found if found else None


def _openroad_available() -> bool:
    """Check whether openroad can be found."""
    return _get_openroad_exe() is not None


def _import_available() -> bool:
    """Check whether ImageMagick ``import`` is on PATH."""
    return shutil.which("import") is not None


def _find_free_display() -> int:
    """Return the first display number without an X lock file."""
    start = settings.GUI_DISPLAY_START
    end = settings.GUI_DISPLAY_END
    for num in range(start, end):
        lock = Path(f"/tmp/.X{num}-lock")
        if not lock.exists():
            return num
    # Fallback – use a high random number outside the configured range
    return start + uuid.uuid4().int % 200


async def _wait_for_display(display_num: int) -> bool:
    """Poll *xdpyinfo* until the display is ready or the timeout expires.

    Returns ``True`` when the display is responsive, ``False`` on timeout.
    The timeout and polling interval are read from
    ``settings.GUI_STARTUP_TIMEOUT_S`` and
    ``settings.GUI_STARTUP_POLL_INTERVAL_S``.
    """
    timeout = settings.GUI_STARTUP_TIMEOUT_S
    interval = settings.GUI_STARTUP_POLL_INTERVAL_S
    display_env = {**os.environ, "DISPLAY": f":{display_num}"}
    elapsed = 0.0

    while elapsed < timeout:
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdpyinfo",
                env=display_env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            rc = await asyncio.wait_for(proc.wait(), timeout=3.0)
            if rc == 0:
                logger.debug("Display :%d ready after %.1fs", display_num, elapsed)
                return True
        except (TimeoutError, OSError):
            pass
        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(
        "Display :%d not ready after %.1fs – proceeding anyway",
        display_num,
        timeout,
    )
    return False


async def _wait_for_gui_ready(display_num: int) -> bool:
    """Poll *xwininfo -root -children* until a real application window appears.

    ``_wait_for_display`` only confirms that Xvfb is accepting connections.
    This function waits for OpenROAD's Qt GUI to create a child window on
    the root, meaning the application has actually rendered.

    Returns ``True`` when an application window is detected, ``False`` on
    timeout.
    """
    timeout = settings.GUI_APP_READY_TIMEOUT_S
    interval = settings.GUI_APP_READY_POLL_INTERVAL_S
    display_env = {**os.environ, "DISPLAY": f":{display_num}"}
    elapsed = 0.0

    while elapsed < timeout:
        try:
            proc = await asyncio.create_subprocess_exec(
                "xwininfo",
                "-root",
                "-children",
                env=display_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            if proc.returncode == 0:
                output = stdout.decode("utf-8", errors="replace")
                # Count lines that look like real child windows.
                # xwininfo output for children has lines like:
                #   0x1400001 (has no name): ("openroad" "OpenROAD")  1280x1024+0+0...
                # We look for indented hex window IDs under the "children:" section.
                child_lines = [
                    line
                    for line in output.splitlines()
                    if line.strip().startswith("0x") and "child" not in line.lower()
                ]
                if child_lines:
                    logger.debug(
                        "GUI window detected on :%d after %.1fs (%d children)",
                        display_num,
                        elapsed,
                        len(child_lines),
                    )
                    return True
        except (TimeoutError, OSError):
            pass
        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(
        "No GUI window detected on :%d after %.1fs -- proceeding anyway",
        display_num,
        timeout,
    )
    return False


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class GuiScreenshotTool(BaseTool):
    """Capture a screenshot from an OpenROAD GUI session running under Xvfb.

    Screenshots are taken by grabbing the X11 root window with
    ImageMagick's ``import`` utility rather than by sending Tcl commands
    through the PTY (which OpenROAD ignores in GUI mode).
    """

    def __init__(self, manager: OpenROADManager) -> None:
        super().__init__(manager)
        # session_id  →  display number used by its Xvfb
        self._session_displays: dict[str, int] = {}
        # session_id  →  Xvfb subprocess PID (for cleanup)
        self._xvfb_pids: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        session_id: str | None = None,
        resolution: str | None = None,
        output_path: str | None = None,
        timeout_ms: int | None = None,
        image_format: str | None = None,
        quality: int | None = None,
        scale: float | None = None,
        crop: str | None = None,
        return_mode: str | None = None,
    ) -> str:
        """Take a GUI screenshot.

        Parameters
        ----------
        session_id:
            Existing GUI-enabled session to reuse.  When *None* a fresh
            headless GUI session is created automatically.
        resolution:
            Virtual display size, e.g. ``"1920x1080x24"``.
            Defaults to ``1280x1024x24``.
        output_path:
            Where to write the final image on disk.  A temp file is used
            when omitted.
        timeout_ms:
            How long to wait for the screenshot capture (default 8 000 ms).
        image_format:
            Output format: ``"png"``, ``"jpeg"``, or ``"webp"``.
            Defaults to ``settings.GUI_DEFAULT_IMAGE_FORMAT``.
        quality:
            Compression quality for JPEG/WebP (1–100).
            Ignored for PNG.  Defaults to
            ``settings.GUI_DEFAULT_JPEG_QUALITY``.
        scale:
            Downscale factor (0.0–1.0].  ``0.5`` produces an image at
            half the original dimensions.  Defaults to ``1.0`` (no
            scaling).
        crop:
            Pixel region to crop: ``"x0 y0 x1 y1"``.  Applied *before*
            scaling.  Omit to keep the full image.
        return_mode:
            How to return the result:

            * ``"base64"`` – full image as base-64 (default)
            * ``"path"``  – file path only, no image data (saves tokens)
            * ``"preview"`` – 256 px thumbnail as base-64 + file path
        """
        # ---- Normalise inputs ----
        # MCP Inspector / FastMCP may pass empty strings for optional
        # parameters the user left blank.  Treat "" the same as None.
        if not image_format:  # None or ""
            image_format = None
        if not return_mode:
            return_mode = None
        if not resolution:
            resolution = None
        if not output_path:
            output_path = None
        if not crop:
            crop = None

        actual_timeout = timeout_ms or settings.GUI_CAPTURE_TIMEOUT_MS
        actual_resolution = resolution or settings.GUI_DISPLAY_RESOLUTION

        # If the user did not specify image_format but provided an output_path
        # with a recognised extension, infer the format from the path.
        _ext_to_fmt: dict[str, str] = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}
        if image_format is None and output_path:
            inferred = _ext_to_fmt.get(Path(output_path).suffix.lower())
            if inferred:
                image_format = inferred

        fmt = (image_format or settings.GUI_DEFAULT_IMAGE_FORMAT).lower()
        actual_quality = quality if quality is not None else settings.GUI_DEFAULT_JPEG_QUALITY
        actual_scale = scale if scale is not None else 1.0
        mode = (return_mode or "base64").lower()

        # ---- Validate parameters early ----
        if fmt not in _VALID_FORMATS:
            return self._format_result(
                GuiScreenshotResult(
                    error="InvalidParameter",
                    message=(f"Unsupported image format '{fmt}'. Choose from: {', '.join(sorted(_VALID_FORMATS))}."),
                )
            )
        if mode not in _VALID_RETURN_MODES:
            return self._format_result(
                GuiScreenshotResult(
                    error="InvalidParameter",
                    message=(
                        f"Unsupported return_mode '{mode}'. Choose from: {', '.join(sorted(_VALID_RETURN_MODES))}."
                    ),
                )
            )
        if not (0.0 < actual_scale <= 1.0):
            return self._format_result(
                GuiScreenshotResult(
                    error="InvalidParameter",
                    message="scale must be between 0.0 (exclusive) and 1.0 (inclusive).",
                )
            )
        if not (1 <= actual_quality <= 100):
            return self._format_result(
                GuiScreenshotResult(
                    error="InvalidParameter",
                    message="quality must be between 1 and 100.",
                )
            )

        try:
            # ----------------------------------------------------------
            # 1.  Ensure we have a GUI-capable session
            # ----------------------------------------------------------
            if session_id is None:
                session_id = await self._create_gui_session(actual_resolution)
                if session_id.startswith("{"):
                    # _create_gui_session returned a JSON error string
                    return session_id

            display_num = self._session_displays.get(session_id)
            if display_num is None:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="SessionNotFound",
                        message=(
                            f"Session {session_id} has no associated X display.  "
                            "Only sessions created by gui_screenshot can be reused."
                        ),
                    )
                )

            # ----------------------------------------------------------
            # 2.  Determine raw capture path (always PNG from import)
            # ----------------------------------------------------------
            tmp_dir = Path(tempfile.gettempdir())
            raw_name = f"openroad_gui_raw_{uuid.uuid4().hex[:12]}.png"
            raw_path = tmp_dir / raw_name
            raw_path.unlink(missing_ok=True)

            # ----------------------------------------------------------
            # 3.  Capture the X11 root window via ImageMagick import
            # ----------------------------------------------------------
            display_env = {**os.environ, "DISPLAY": f":{display_num}"}
            import_timeout = actual_timeout / 1000.0

            proc = await asyncio.create_subprocess_exec(
                "import",
                "-window",
                "root",
                str(raw_path),
                env=display_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=import_timeout,
                )
            except TimeoutError:
                proc.kill()
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="ScreenshotFailed",
                        message=(
                            f"ImageMagick import timed out after {import_timeout:.0f}s.  "
                            "The Xvfb display may not be responding."
                        ),
                    )
                )

            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace")[:500]
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="ScreenshotFailed",
                        message=f"ImageMagick import failed (rc={proc.returncode}): {err_text}",
                    )
                )

            if not raw_path.exists() or raw_path.stat().st_size == 0:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="ScreenshotFailed",
                        message=f"Screenshot file was not created at {raw_path}.",
                    )
                )

            original_size = raw_path.stat().st_size

            # ----------------------------------------------------------
            # 4.  Post-process: crop → scale → format conversion
            # ----------------------------------------------------------
            img: Image.Image = Image.open(raw_path)

            # Crop (pixel coordinates: "x0 y0 x1 y1")
            if crop:
                try:
                    coords = tuple(int(c) for c in crop.split())
                    if len(coords) != 4:
                        raise ValueError("Expected 4 integers")
                    img = img.crop(coords)
                except (ValueError, TypeError) as e:
                    img.close()
                    return self._format_result(
                        GuiScreenshotResult(
                            session_id=session_id,
                            error="InvalidParameter",
                            message=(
                                f"Invalid crop value '{crop}'. "
                                "Expected 4 space-separated pixel coordinates: 'x0 y0 x1 y1'. "
                                f"Error: {e}"
                            ),
                        )
                    )

            # Scale
            if actual_scale < 1.0:
                new_w = max(int(img.width * actual_scale), 1)
                new_h = max(int(img.height * actual_scale), 1)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            final_w, final_h = img.size

            # Convert to output format in-memory
            pil_format_map = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
            pil_fmt = pil_format_map[fmt]

            # JPEG doesn't support alpha — convert RGBA → RGB
            if fmt == "jpeg" and img.mode in ("RGBA", "LA", "PA"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            save_kwargs: dict[str, int] = {}
            if fmt in ("jpeg", "webp"):
                save_kwargs["quality"] = actual_quality
            img.save(buf, format=pil_fmt, **save_kwargs)
            img.close()

            processed_bytes = buf.getvalue()
            processed_size = len(processed_bytes)

            # ----------------------------------------------------------
            # 5.  File size check
            # ----------------------------------------------------------
            max_size = settings.GUI_MAX_SCREENSHOT_SIZE_MB
            file_size_mb = processed_size / (1024 * 1024)
            if file_size_mb > max_size:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="FileTooLarge",
                        message=(
                            f"Screenshot size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({max_size} MB)."
                        ),
                    )
                )

            # ----------------------------------------------------------
            # 6.  Write final file & build result
            # ----------------------------------------------------------
            ext_map = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
            if output_path:
                final_path = Path(output_path)
                # Ensure the correct extension matches the requested format
                expected_ext = ext_map[fmt]
                if final_path.suffix.lower() not in (expected_ext, expected_ext.replace(".", "")):
                    # Append or replace extension to match format
                    final_path = final_path.with_suffix(expected_ext)
                # Create parent directories if they don't exist
                final_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                final_name = f"openroad_gui_{uuid.uuid4().hex[:12]}{ext_map[fmt]}"
                final_path = tmp_dir / final_name

            final_path.write_bytes(processed_bytes)

            # Clean up raw capture
            raw_path.unlink(missing_ok=True)

            compression_applied = fmt != "png" or actual_scale < 1.0 or crop is not None
            compression_ratio = processed_size / original_size if compression_applied and original_size > 0 else None
            now = datetime.now().isoformat()

            if mode == "path":
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        image_path=str(final_path),
                        image_format=fmt,
                        size_bytes=processed_size,
                        original_size_bytes=original_size,
                        resolution=actual_resolution,
                        timestamp=now,
                        return_mode=mode,
                        compression_applied=compression_applied,
                        compression_ratio=compression_ratio,
                        width=final_w,
                        height=final_h,
                        message=(f"Screenshot saved to {final_path} ({processed_size:,} bytes, {fmt})."),
                    )
                )

            if mode == "preview":
                # Generate a small thumbnail for preview
                preview_img: Image.Image = Image.open(io.BytesIO(processed_bytes))
                preview_img.thumbnail((_PREVIEW_SIZE, _PREVIEW_SIZE), Image.Resampling.LANCZOS)
                preview_buf = io.BytesIO()
                if fmt == "jpeg" and preview_img.mode in ("RGBA", "LA", "PA"):
                    preview_img = preview_img.convert("RGB")
                preview_img.save(preview_buf, format=pil_fmt, **save_kwargs)
                preview_img.close()
                preview_b64 = base64.b64encode(preview_buf.getvalue()).decode("utf-8")
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        image_data=preview_b64,
                        image_path=str(final_path),
                        image_format=fmt,
                        size_bytes=processed_size,
                        original_size_bytes=original_size,
                        resolution=actual_resolution,
                        timestamp=now,
                        return_mode=mode,
                        compression_applied=compression_applied,
                        compression_ratio=compression_ratio,
                        width=final_w,
                        height=final_h,
                        message=(
                            f"Preview thumbnail ({_PREVIEW_SIZE}px) returned. "
                            f"Full image at {final_path} "
                            f"({processed_size:,} bytes, {fmt})."
                        ),
                    )
                )

            # mode == "base64"  (default)
            image_b64 = base64.b64encode(processed_bytes).decode("utf-8")
            return self._format_result(
                GuiScreenshotResult(
                    session_id=session_id,
                    image_data=image_b64,
                    image_path=str(final_path),
                    image_format=fmt,
                    size_bytes=processed_size,
                    original_size_bytes=original_size,
                    resolution=actual_resolution,
                    timestamp=now,
                    return_mode=mode,
                    compression_applied=compression_applied,
                    compression_ratio=compression_ratio,
                    width=final_w,
                    height=final_h,
                    message="Screenshot captured successfully.",
                )
            )

        except SessionNotFoundError as e:
            logger.warning("GUI session not found: %s", session_id)
            return self._format_result(
                GuiScreenshotResult(
                    session_id=session_id,
                    error="SessionNotFound",
                    message=str(e),
                )
            )

        except (SessionTerminatedError, SessionError) as e:
            logger.error("GUI session error for %s: %s", session_id, e)
            return self._format_result(
                GuiScreenshotResult(
                    session_id=session_id,
                    error="SessionError",
                    message=str(e),
                )
            )

        except Exception as e:
            logger.exception("Unexpected error capturing GUI screenshot")
            return self._format_result(
                GuiScreenshotResult(
                    session_id=session_id,
                    error="UnexpectedError",
                    message=f"Failed to capture GUI screenshot: {e}",
                )
            )

    # ------------------------------------------------------------------
    # Cleanup helper – call when tearing down sessions
    # ------------------------------------------------------------------

    def cleanup_display(self, session_id: str) -> None:
        """Kill the Xvfb process associated with *session_id*."""
        pid = self._xvfb_pids.pop(session_id, None)
        self._session_displays.pop(session_id, None)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info("Killed Xvfb (pid %d) for session %s", pid, session_id)
            except OSError:
                pass  # already dead

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _create_gui_session(self, resolution: str) -> str:
        """Start Xvfb + OpenROAD and return the new session id.

        Returns either a valid session-id string or a pre-formatted JSON
        error string (starts with ``{``).
        """
        if not _xvfb_available():
            return self._format_result(
                GuiScreenshotResult(
                    error="XvfbNotFound",
                    message="Xvfb is not installed.  Install it with: apt-get install -y xvfb",
                )
            )

        openroad_exe = _get_openroad_exe()
        if openroad_exe is None:
            return self._format_result(
                GuiScreenshotResult(
                    error="OpenROADNotFound",
                    message=(
                        "openroad is not installed or not on PATH.  "
                        "Set the OPENROAD_EXE environment variable to the "
                        "full path of the openroad binary, or add its "
                        "directory to PATH.  "
                        "See https://openroad.readthedocs.io/ for installation."
                    ),
                )
            )

        if not _import_available():
            return self._format_result(
                GuiScreenshotResult(
                    error="ImportNotFound",
                    message=("ImageMagick 'import' is not installed.  Install it with: apt-get install -y imagemagick"),
                )
            )

        # --- Start Xvfb on a free display ---
        display_num = _find_free_display()

        xvfb_proc = await asyncio.create_subprocess_exec(
            "Xvfb",
            f":{display_num}",
            "-screen",
            "0",
            resolution,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # Give Xvfb a moment to bind the display socket
        await asyncio.sleep(1.0)

        # Check that Xvfb is still running
        if xvfb_proc.returncode is not None:
            return self._format_result(
                GuiScreenshotResult(
                    error="XvfbStartFailed",
                    message=f"Xvfb exited immediately (rc={xvfb_proc.returncode}) on display :{display_num}.",
                )
            )

        # --- Start OpenROAD on that display ---
        session_id = await self.manager.create_session(
            command=[openroad_exe, "-gui", "-no_init"],
            env={"DISPLAY": f":{display_num}"},
        )

        self._session_displays[session_id] = display_num
        self._xvfb_pids[session_id] = xvfb_proc.pid
        logger.info(
            "Created headless GUI session %s on display :%d (Xvfb pid %d)",
            session_id,
            display_num,
            xvfb_proc.pid,
        )

        # Wait for the X11 display to become ready (replaces fixed sleep)
        await _wait_for_display(display_num)

        # Wait for OpenROAD GUI to create an actual window (prevents
        # capturing a blank/black frame before the app has rendered).
        await _wait_for_gui_ready(display_num)

        return session_id
