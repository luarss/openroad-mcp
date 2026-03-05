"""GUI screenshot tool for headless OpenROAD GUI sessions."""

import asyncio
import base64
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from ..core.models import GuiScreenshotResult
from ..interactive.models import SessionError, SessionNotFoundError, SessionTerminatedError
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("gui_tools")

# Default virtual framebuffer geometry
DEFAULT_DISPLAY_RESOLUTION = "1280x1024x24"

# Timeout for GUI startup and image capture (ms)
GUI_STARTUP_TIMEOUT_MS = 10_000
IMAGE_CAPTURE_TIMEOUT_MS = 8_000

# Maximum screenshot file size (MB)
MAX_SCREENSHOT_SIZE_MB = 50

# Tcl template: open the GUI, wait for rendering, save the image, then continue
# The `after` callbacks give the GUI event loop time to render before capture.
_SAVE_IMAGE_TCL = 'gui::save_image "{path}"'

# Polling settings for waiting on the screenshot file
_FILE_POLL_INTERVAL = 0.5  # seconds between polls
_FILE_POLL_MAX_WAIT = 5.0  # total seconds to wait for non-empty file


def _xvfb_available() -> bool:
    """Check whether xvfb-run is on PATH."""
    return shutil.which("xvfb-run") is not None


class GuiScreenshotTool(BaseTool):
    """Capture a screenshot from an OpenROAD GUI session running under Xvfb."""

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
            ``xvfb-run openroad -gui`` session is created automatically.
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
                if not _xvfb_available():
                    return self._format_result(
                        GuiScreenshotResult(
                            error="XvfbNotFound",
                            message=("xvfb-run is not installed.  Install it with: apt-get install -y xvfb"),
                        )
                    )

                session_id = await self.manager.create_session(
                    command=[
                        "xvfb-run",
                        "-a",  # auto-pick a free display
                        "-s",
                        f"-screen 0 {actual_resolution}",
                        "openroad",
                        "-gui",
                        "-no_init",
                    ],
                )
                logger.info("Created headless GUI session %s", session_id)

                # Give the GUI event loop time to initialise
                await asyncio.sleep(3.0)

            # ----------------------------------------------------------
            # 2.  Determine output file path
            # ----------------------------------------------------------
            if output_path:
                image_path = Path(output_path)
            else:
                # Build a path without pre-creating the file so we can
                # reliably detect whether gui::save_image wrote anything.
                tmp_dir = Path(tempfile.gettempdir())
                tmp_name = f"openroad_gui_{uuid.uuid4().hex[:12]}.png"
                image_path = tmp_dir / tmp_name

            # Remove any stale file so the existence check is meaningful
            image_path.unlink(missing_ok=True)

            # ----------------------------------------------------------
            # 3.  Ask OpenROAD to save the current view
            # ----------------------------------------------------------
            save_cmd = _SAVE_IMAGE_TCL.format(path=image_path)
            result = await self.manager.execute_command(
                session_id,
                save_cmd,
                actual_timeout,
            )

            # ----------------------------------------------------------
            # 3b. Poll until the file appears with non-zero content.
            #     gui::save_image may need several event-loop ticks to
            #     render the frame buffer and flush the PNG to disk.
            # ----------------------------------------------------------
            elapsed = 0.0
            while elapsed < _FILE_POLL_MAX_WAIT:
                if image_path.exists() and image_path.stat().st_size > 0:
                    break
                await asyncio.sleep(_FILE_POLL_INTERVAL)
                elapsed += _FILE_POLL_INTERVAL

            # ----------------------------------------------------------
            # 4.  Read the image and return base64-encoded data
            # ----------------------------------------------------------
            if not image_path.exists() or image_path.stat().st_size == 0:
                return self._format_result(
                    GuiScreenshotResult(
                        session_id=session_id,
                        error="ScreenshotFailed",
                        message=(
                            f"Screenshot file was not created (or is empty) at {image_path}.  "
                            "The GUI may not have finished rendering yet.  "
                            f"OpenROAD output: {result.output[:500]}"
                        ),
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
