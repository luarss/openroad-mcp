"""Main MCP server setup and tool registration."""

import asyncio

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from openroad_mcp.config.cli import CLIConfig

from .core.manager import OpenROADManager
from .core.models import (
    InteractiveExecResult,
    InteractiveSessionInfo,
    InteractiveSessionListResult,
    ListImagesResult,
    ReadImageResult,
    SessionHistoryResult,
    SessionInspectionResult,
    SessionMetricsResult,
    SessionTerminationResult,
)
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

# Pre-compute output schemas at module load time
_EXEC_SCHEMA = InteractiveExecResult.model_json_schema()
_SESSION_INFO_SCHEMA = InteractiveSessionInfo.model_json_schema()
_SESSION_LIST_SCHEMA = InteractiveSessionListResult.model_json_schema()
_TERMINATION_SCHEMA = SessionTerminationResult.model_json_schema()
_INSPECTION_SCHEMA = SessionInspectionResult.model_json_schema()
_HISTORY_SCHEMA = SessionHistoryResult.model_json_schema()
_METRICS_SCHEMA = SessionMetricsResult.model_json_schema()
_LIST_IMAGES_SCHEMA = ListImagesResult.model_json_schema()
_READ_IMAGE_SCHEMA = ReadImageResult.model_json_schema()


# Interactive session tools
@mcp.tool(
    output_schema=_EXEC_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def interactive_openroad(command: str, session_id: str | None = None, timeout_ms: int | None = None) -> str:
    """Execute a Tcl/OpenROAD command in an interactive PTY session.

    Runs the given Tcl expression inside a persistent OpenROAD process. If no
    session_id is provided a new session is created automatically.  Risky or
    unrecognised commands (exec, source, exit, …) are intercepted and a
    permission-request is returned instead of executing; pass confirmed=True to
    override.

    Returns a JSON object matching InteractiveExecResult:
      - output (str): combined stdout/stderr captured from the PTY
      - session_id (str|null): the session that ran the command
      - timestamp (str): ISO-8601 wall-clock time at execution start
      - execution_time (float): wall-clock seconds for the command
      - command_count (int): total commands run in this session
      - buffer_size (int): current PTY output buffer size in bytes
      - error (str|null): human-readable error message if the call failed
      - error_code (str|null): 'not_found'|'not_permitted'|'temporary_failure'|null
    """
    return await interactive_shell_tool.execute(command, session_id, timeout_ms)


@mcp.tool(
    output_schema=_SESSION_LIST_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def list_interactive_sessions() -> str:
    """List all active interactive OpenROAD sessions.

    Returns a JSON object matching InteractiveSessionListResult:
      - sessions (list[InteractiveSessionInfo]): details for each session
      - total_count (int): total number of sessions (active + terminated)
      - active_count (int): number of currently alive sessions
      - error (str|null): error message if the listing failed
      - error_code (str|null): 'temporary_failure'|null
    """
    return await list_sessions_tool.execute()


@mcp.tool(
    output_schema=_SESSION_INFO_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def create_interactive_session(
    session_id: str | None = None,
    command: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str:
    """Create a new interactive OpenROAD PTY session.

    Spawns a new OpenROAD process with an attached pseudo-terminal. The optional
    session_id lets callers name the session for later reference; a UUID is
    generated when omitted.  Use command to override the default openroad binary,
    env to inject environment variables, and cwd to set the working directory.

    Returns a JSON object matching InteractiveSessionInfo:
      - session_id (str): unique identifier for the created session
      - created_at (str): ISO-8601 creation timestamp
      - is_alive (bool): whether the session process is running
      - command_count (int): commands executed so far (0 on creation)
      - buffer_size (int): current PTY output buffer size in bytes
      - uptime_seconds (float|null): seconds since session creation
      - state (str|null): 'creating'|'active'|'terminated'|'error'
      - error (str|null): error message if session creation failed
      - error_code (str|null): 'temporary_failure'|null
    """
    return await create_session_tool.execute(session_id, command, env, cwd)


@mcp.tool(
    output_schema=_TERMINATION_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
async def terminate_interactive_session(session_id: str, force: bool = False) -> str:
    """Terminate an interactive OpenROAD session.

    Sends SIGTERM (or SIGKILL when force=True) to the session process and
    cleans up associated resources.  Terminating a non-existent session returns
    error_code='not_found'.

    Returns a JSON object matching SessionTerminationResult:
      - session_id (str): the session that was targeted
      - terminated (bool): True if the session was successfully stopped
      - was_alive (bool): whether the session was alive before termination
      - force (bool): whether SIGKILL was used
      - error (str|null): error message if termination failed
      - error_code (str|null): 'not_found'|'temporary_failure'|null
    """
    return await terminate_session_tool.execute(session_id, force)


@mcp.tool(
    output_schema=_INSPECTION_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def inspect_interactive_session(session_id: str, detail: str = "standard") -> str:
    """Get detailed inspection data for an interactive OpenROAD session.

    Retrieves runtime metrics for the specified session.  The detail parameter
    controls verbosity: 'minimal' returns only session identity and state,
    'standard' (default) adds command and performance aggregates, 'full' includes
    buffer and timeout internals.

    Returns a JSON object matching SessionInspectionResult:
      - session_id (str): the inspected session
      - metrics (dict|null): nested metrics dict; structure varies by detail level:
          minimal  — session_id, state, is_alive, created_at, uptime_seconds
          standard — adds commands and performance sections
          full     — adds buffer and timeout sections
      - error (str|null): error message if inspection failed
      - error_code (str|null): 'not_found'|'temporary_failure'|null
    """
    return await inspect_session_tool.execute(session_id, detail)


@mcp.tool(
    output_schema=_HISTORY_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def get_session_history(session_id: str, limit: int | None = None, search: str | None = None) -> str:
    """Get command history for an interactive OpenROAD session.

    Returns the ordered list of Tcl commands executed in the session, newest
    first.  Use limit to cap the number of returned records and search to filter
    by a case-insensitive substring match against command text.

    Returns a JSON object matching SessionHistoryResult:
      - session_id (str): the queried session
      - history (list[dict]): command records with command, timestamp, and id fields
      - total_commands (int): number of records returned (after filtering)
      - limit (int|null): the limit applied, if any
      - search (str|null): the search string applied, if any
      - error (str|null): error message if retrieval failed
      - error_code (str|null): 'not_found'|'temporary_failure'|null
    """
    return await session_history_tool.execute(session_id, limit, search)


@mcp.tool(
    output_schema=_METRICS_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def get_session_metrics(detail: str = "standard") -> str:
    """Get comprehensive metrics for all interactive OpenROAD sessions.

    Aggregates resource usage and command statistics across every managed
    session.  The detail parameter controls verbosity: 'minimal' returns only
    manager-level counts, 'standard' (default) adds aggregate totals, 'full'
    includes a per-session breakdown.

    Returns a JSON object matching SessionMetricsResult:
      - metrics (dict|null): nested metrics dict; structure varies by detail level:
          minimal  — manager section: total_sessions, active_sessions, max_sessions, utilization_percent
          standard — adds aggregate section: total_commands, total_cpu_time, total_memory_mb
          full     — adds sessions list with per-session detailed metrics
      - error (str|null): error message if retrieval failed
      - error_code (str|null): 'temporary_failure'|null
    """
    return await session_metrics_tool.execute(detail)


# Report image tools
@mcp.tool(
    output_schema=_LIST_IMAGES_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def list_report_images(platform: str, design: str, run_slug: str, stage: str = "all") -> str:
    """List available report images from ORFS runs organized by stage.

    Scans the ORFS reports directory for the given platform/design/run_slug
    combination and returns metadata for every .webp image found.  Use stage to
    filter to a single flow stage (e.g. 'cts', 'final'); the default 'all'
    returns images from every stage.

    Returns a JSON object matching ListImagesResult:
      - run_path (str|null): absolute path to the run directory
      - total_images (int|null): total number of matching images
      - images_by_stage (dict|null): stage name → list of ImageInfo objects,
          each with filename, path, size_bytes, modified_time, and type fields
      - message (str|null): informational message (e.g. when no images found)
      - error (str|null): error message if listing failed
      - error_code (str|null): 'not_found'|'invalid_input'|'temporary_failure'|null
    """
    return await list_report_images_tool.execute(platform, design, run_slug, stage)


@mcp.tool(
    output_schema=_READ_IMAGE_SCHEMA,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def read_report_image(platform: str, design: str, run_slug: str, image_name: str) -> str:
    """Read a report image and return base64-encoded data with metadata.

    Loads the specified .webp image from the ORFS reports directory, applies
    LANCZOS downscaling + WEBP re-compression when the base64-encoded size
    would exceed 15 KB, and returns the result with full provenance metadata.

    Returns a JSON object matching ReadImageResult:
      - image_data (str|null): base64-encoded image bytes (WEBP format)
      - metadata (ImageMetadata|null): filename, format, size_bytes, width, height,
          modified_time, stage, type, compression_applied, compression_ratio,
          original_size_bytes, original_width, original_height
      - message (str|null): informational message
      - error (str|null): error message if reading failed
      - error_code (str|null): 'not_found'|'invalid_input'|'temporary_failure'|null
    """
    return await read_report_image_tool.execute(platform, design, run_slug, image_name)


async def shutdown_openroad() -> None:
    """Gracefully shutdown interactive OpenROAD sessions."""
    try:
        logger.info("Initiating graceful shutdown of OpenROAD services...")

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
