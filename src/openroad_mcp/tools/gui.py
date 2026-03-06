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
3. Sleep for a few seconds so Qt / OpenGL can initialise.
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

from ..core.manager import OpenROADManager
from ..core.models import GuiScreenshotResult
from ..interactive.models import SessionError, SessionNotFoundError, SessionTerminatedError
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("gui_tools")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default virtual framebuffer geometry  (WxHxDepth)
DEFAULT_DISPLAY_RESOLUTION = "1280x1024x24"

# Timeout defaults (ms)
GUI_STARTUP_TIMEOUT_MS = 10_000
IMAGE_CAPTURE_TIMEOUT_MS = 8_000

# Maximum screenshot file size (MB)
MAX_SCREENSHOT_SIZE_MB = 50

# How long to sleep after starting OpenROAD before capturing.
# In Docker the Qt / OpenGL init takes 4-6 s.
_GUI_INIT_SLEEP = 6.0

# Timeout for the ``import`` subprocess (seconds)
_IMPORT_TIMEOUT = 15.0

# Range of X11 display numbers to try when looking for a free one
_DISPLAY_RANGE = range(42, 100)


# ---------------------------------------------------------------------------
# Pre-flight helpers
# ---------------------------------------------------------------------------


def _xvfb_available() -> bool:
    """Check whether Xvfb is on PATH."""
    return shutil.which("Xvfb") is not None


def _openroad_available() -> bool:
    """Check whether openroad is on PATH."""
    return shutil.which("openroad") is not None


def _import_available() -> bool:
    """Check whether ImageMagick ``import`` is on PATH."""
    return shutil.which("import") is not None


def _find_free_display() -> int:
    """Return the first display number without an X lock file."""
    for num in _DISPLAY_RANGE:
        lock = Path(f"/tmp/.X{num}-lock")
        if not lock.exists():
            return num
    # Fallback – use a high random number
    return 42 + uuid.uuid4().int % 200


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
        actual_timeout = timeout_ms or IMAGE_CAPTURE_TIMEOUT_MS
        actual_resolution = resolution or DEFAULT_DISPLAY_RESOLUTION

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

            file_size_mb = image_path.stat().st_size / (1024 * 1024)
            if file_size_mb > MAX_SCREENSHOT_SIZE_MB:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="FileTooLarge",
                        message=(
                            f"Screenshot size ({file_size_mb:.2f} MB) exceeds "
                            f"maximum allowed size ({MAX_SCREENSHOT_SIZE_MB} MB)."
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

        if not _openroad_available():
            return self._format_result(
                GuiScreenshotResult(
                    error="OpenROADNotFound",
                    message=(
                        "openroad is not installed or not on PATH.  "
                        "GUI screenshots require OpenROAD with GUI support.  "
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
            command=["openroad", "-gui", "-no_init"],
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

        # Wait for Qt / OpenGL to finish initialising
        await asyncio.sleep(_GUI_INIT_SLEEP)

        return session_id
