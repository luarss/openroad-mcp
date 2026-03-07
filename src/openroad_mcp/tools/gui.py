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
5. Read the resulting PNG and return it as base-64.
"""

import asyncio
import base64
import os
import shutil
import signal
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

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
            Where to write the PNG on disk.  A temp file is used when omitted.
        timeout_ms:
            How long to wait for the screenshot capture (default 8 000 ms).
        """
        actual_timeout = timeout_ms or settings.GUI_CAPTURE_TIMEOUT_MS
        actual_resolution = resolution or settings.GUI_DISPLAY_RESOLUTION

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
            # 2.  Determine output file path
            # ----------------------------------------------------------
            if output_path:
                image_path = Path(output_path)
            else:
                tmp_dir = Path(tempfile.gettempdir())
                tmp_name = f"openroad_gui_{uuid.uuid4().hex[:12]}.png"
                image_path = tmp_dir / tmp_name

            image_path.unlink(missing_ok=True)

            # ----------------------------------------------------------
            # 3.  Capture the X11 root window via ImageMagick import
            # ----------------------------------------------------------
            display_env = {**os.environ, "DISPLAY": f":{display_num}"}
            import_timeout = actual_timeout / 1000.0

            proc = await asyncio.create_subprocess_exec(
                "import",
                "-window",
                "root",
                str(image_path),
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

            # ----------------------------------------------------------
            # 4.  Validate & return the captured image
            # ----------------------------------------------------------
            if not image_path.exists() or image_path.stat().st_size == 0:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="ScreenshotFailed",
                        message=f"Screenshot file was not created at {image_path}.",
                    )
                )

            max_size = settings.GUI_MAX_SCREENSHOT_SIZE_MB
            file_size_mb = image_path.stat().st_size / (1024 * 1024)
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

            image_data = image_path.read_bytes()
            image_b64 = base64.b64encode(image_data).decode("utf-8")

            return self._format_result(
                GuiScreenshotResult(
                    session_id=session_id,
                    image_data=image_b64,
                    image_path=str(image_path),
                    image_format="png",
                    size_bytes=len(image_data),
                    resolution=actual_resolution,
                    timestamp=datetime.now().isoformat(),
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

        return session_id
