"""Main MCP server setup and tool registration."""

import asyncio
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from openroad_mcp.config.cli import CLIConfig

from .core.manager import OpenROADManager
from .tools.gui import GuiScreenshotTool
from .tools.interactive import (
    CreateSessionTool,
    InspectSessionTool,
    InteractiveShellTool,
    ListSessionsTool,
    SessionHistoryTool,
    SessionMetricsTool,
    TerminateSessionTool,
)
from .tools.report_images import ListReportImagesTool, ReadReportImageTool
from .utils.cleanup import cleanup_manager
from .utils.logging import get_logger

logger = get_logger("server")

# Initialize FastMCP
mcp: FastMCP = FastMCP("openroad-mcp")

# Global manager instance
manager = OpenROADManager()

# Initialize interactive tool instances
interactive_shell_tool = InteractiveShellTool(manager)
list_sessions_tool = ListSessionsTool(manager)
create_session_tool = CreateSessionTool(manager)
terminate_session_tool = TerminateSessionTool(manager)
inspect_session_tool = InspectSessionTool(manager)
session_history_tool = SessionHistoryTool(manager)
session_metrics_tool = SessionMetricsTool(manager)

# Initialize report image tool instances
list_report_images_tool = ListReportImagesTool(manager)
read_report_image_tool = ReadReportImageTool(manager)

# Initialize GUI tool instances
gui_screenshot_tool = GuiScreenshotTool(manager)


# Interactive session tools
@mcp.tool()
async def interactive_openroad(command: str, session_id: str | None = None, timeout_ms: int | None = None) -> str:
    """Execute a command in an interactive OpenROAD session with PTY support."""
    return await interactive_shell_tool.execute(command, session_id, timeout_ms)


@mcp.tool()
async def list_interactive_sessions() -> str:
    """List all active interactive OpenROAD sessions."""
    return await list_sessions_tool.execute()


@mcp.tool()
async def create_interactive_session(
    session_id: str | None = None,
    command: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str:
    """Create a new interactive OpenROAD session."""
    return await create_session_tool.execute(session_id, command, env, cwd)


@mcp.tool()
async def terminate_interactive_session(session_id: str, force: bool = False) -> str:
    """Terminate an interactive OpenROAD session."""
    return await terminate_session_tool.execute(session_id, force)


@mcp.tool()
async def inspect_interactive_session(session_id: str) -> str:
    """Get detailed inspection data for an interactive OpenROAD session."""
    return await inspect_session_tool.execute(session_id)


@mcp.tool()
async def get_session_history(session_id: str, limit: int | None = None, search: str | None = None) -> str:
    """Get command history for an interactive OpenROAD session."""
    return await session_history_tool.execute(session_id, limit, search)


@mcp.tool()
async def get_session_metrics() -> str:
    """Get comprehensive metrics for all interactive OpenROAD sessions."""
    return await session_metrics_tool.execute()


# Report image tools
@mcp.tool()
async def list_report_images(platform: str, design: str, run_slug: str, stage: str = "all") -> str:
    """List available report images from ORFS runs organized by stage."""
    return await list_report_images_tool.execute(platform, design, run_slug, stage)


@mcp.tool()
async def read_report_image(platform: str, design: str, run_slug: str, image_name: str) -> str:
    """Read a report image and return base64-encoded data with metadata."""
    return await read_report_image_tool.execute(platform, design, run_slug, image_name)


# GUI tools
@mcp.tool()
async def gui_screenshot(
    session_id: Annotated[
        str,
        Field(description="Existing GUI session ID to reuse. Leave empty to auto-create a new headless session."),
    ] = "",
    resolution: Annotated[
        str,
        Field(description="Virtual display resolution, e.g. '1920x1080x24'. Defaults to '1280x1024x24'."),
    ] = "",
    output_path: Annotated[
        str,
        Field(description="File path to save the screenshot on disk. A temp file is used when omitted."),
    ] = "",
    timeout_ms: Annotated[
        str,
        Field(description="Timeout in milliseconds for the screenshot capture. Defaults to 8000."),
    ] = "",
    image_format: Annotated[
        str,
        Field(description="Output format: 'png', 'jpeg', or 'webp'. Defaults to 'jpeg' (smaller, saves tokens)."),
    ] = "",
    quality: Annotated[
        str,
        Field(description="Compression quality for JPEG/WebP (1-100). Ignored for PNG. Defaults to 85."),
    ] = "",
    scale: Annotated[
        str,
        Field(description="Downscale factor (0.0-1.0]. 0.5 = half size. Defaults to 1.0 (no scaling)."),
    ] = "",
    crop: Annotated[
        str,
        Field(
            description=(
                "Pixel region to crop: 'x0,y0,x1,y1' or 'x0 y0 x1 y1'. "
                "Applied before scaling. Leave empty for full image."
            )
        ),
    ] = "",
    return_mode: Annotated[
        str,
        Field(
            description=(
                "How to return the result: "
                "'base64' (full image, default), "
                "'path' (file path only, saves tokens), "
                "'preview' (256px thumbnail + file path)."
            )
        ),
    ] = "",
) -> str:
    """Capture a screenshot of the OpenROAD GUI running in a headless display.

    Auto-creates a session if session_id is not provided. Use return_mode='path'
    or 'preview' to save tokens. JPEG with quality=60-85 reduces size by 70-90%.
    """

    # Normalise inputs: empty strings → None so execute() applies defaults.
    def _clean(v: str) -> str | None:
        v = str(v).strip()
        return v if v else None

    def _int(v: str, name: str = "parameter") -> int | None:
        v = str(v).strip()
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            raise ValueError(f"Invalid integer value for {name}: '{v}'") from None

    def _float(v: str, name: str = "parameter") -> float | None:
        v = str(v).strip()
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            raise ValueError(f"Invalid numeric value for {name}: '{v}'") from None

    try:
        return await gui_screenshot_tool.execute(
            session_id=_clean(session_id),
            resolution=_clean(resolution),
            output_path=_clean(output_path),
            timeout_ms=_int(timeout_ms, "timeout_ms"),
            image_format=_clean(image_format),
            quality=_int(quality, "quality"),
            scale=_float(scale, "scale"),
            crop=_clean(crop),
            return_mode=_clean(return_mode),
        )
    except ValueError as e:
        import json

        from .core.models import GuiScreenshotResult

        return json.dumps(
            GuiScreenshotResult(error="InvalidParameter", message=str(e)).model_dump(),
            indent=2,
        )


async def shutdown_openroad() -> None:
    """Gracefully shutdown interactive OpenROAD sessions and GUI displays."""
    try:
        logger.info("Initiating graceful shutdown of OpenROAD services...")

        # Clean up any Xvfb displays managed by the GUI tool
        for sid in list(gui_screenshot_tool._session_displays):
            gui_screenshot_tool.cleanup_display(sid)

        await manager.cleanup_all()

        logger.info("OpenROAD services shutdown completed successfully")
    except Exception:
        logger.exception("Error during OpenROAD shutdown")


async def run_server(config: CLIConfig) -> None:
    """Main server entry point with lifecycle management."""
    logger.info(f"Starting OpenROAD MCP server in {config.transport.mode} mode...")

    # Create shutdown event for coordinated shutdown
    shutdown_event = asyncio.Event()

    try:
        # Register cleanup handlers
        cleanup_manager.register_async_cleanup_handler(shutdown_openroad)
        cleanup_manager.setup_signal_handlers()
        cleanup_manager.set_shutdown_event(shutdown_event)

        # Run the MCP server with the configured transport in a task
        if config.transport.mode == "stdio":
            logger.info("Using stdio transport")
            server_task = asyncio.create_task(mcp.run_async(transport="stdio"))
        elif config.transport.mode == "http":
            logger.info(f"Using HTTP transport on {config.transport.host}:{config.transport.port}")
            # TODO: Streamable-HTTP
            raise NotImplementedError(
                "Streamable HTTP transport is not yet implemented. "
                "This argument structure is prepared for future implementation. "
                "Please use --transport stdio (default) for now."
            )
        else:
            raise ValueError(f"Unsupported transport mode: {config.transport.mode}")

        # Wait for either server completion or shutdown signal
        shutdown_task = asyncio.create_task(cleanup_manager.wait_for_shutdown())
        _, pending = await asyncio.wait([server_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error in server: {e}")
        raise
    finally:
        # Ensure cleanup happens
        await shutdown_openroad()
        logger.info("OpenROAD MCP server shutdown complete")
