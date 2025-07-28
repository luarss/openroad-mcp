"""Main MCP server setup and tool registration."""

from fastmcp import FastMCP

from openroad_mcp.config.cli import CLIConfig

from .core.manager import OpenROADManager
from .tools.context import GetCommandHistoryTool, GetContextTool
from .tools.process import ExecuteCommandTool, GetStatusTool, RestartProcessTool
from .utils.cleanup import cleanup_manager
from .utils.logging import get_logger

logger = get_logger("server")

# Initialize FastMCP
mcp: FastMCP = FastMCP("openroad-mcp")

# Global manager instance
manager = OpenROADManager()

# Initialize tool instances
execute_command_tool = ExecuteCommandTool(manager)
get_status_tool = GetStatusTool(manager)
restart_process_tool = RestartProcessTool(manager)
get_command_history_tool = GetCommandHistoryTool(manager)
get_context_tool = GetContextTool(manager)


@mcp.tool()
async def execute_openroad_command(command: str, timeout: float | None = None) -> str:
    """Execute a command in the OpenROAD interactive process and return the output."""
    return await execute_command_tool.execute(command, timeout)


@mcp.tool()
async def get_openroad_status() -> str:
    """Get the current status of the OpenROAD process."""
    return await get_status_tool.execute()


@mcp.tool()
async def restart_openroad() -> str:
    """Restart the OpenROAD interactive process."""
    return await restart_process_tool.execute()


@mcp.tool()
async def get_command_history() -> str:
    """Get the command history from the OpenROAD session."""
    return await get_command_history_tool.execute()


@mcp.tool()
async def get_openroad_context() -> str:
    """Get comprehensive context information including status, recent output, and command history."""
    return await get_context_tool.execute()


async def startup_openroad() -> None:
    """Automatically start OpenROAD process on application startup."""
    try:
        logger.info("Starting OpenROAD process automatically...")
        result = await manager.start_process()

        if result.status == "started":
            logger.info(f"OpenROAD process started with PID {result.pid}")
        else:
            logger.warning(f"Failed to start OpenROAD process: {result.message}")
    except Exception as e:
        logger.error(f"Error during automatic OpenROAD startup: {e}")


async def shutdown_openroad() -> None:
    """Gracefully shutdown OpenROAD process."""
    try:
        logger.info("Initiating graceful shutdown of OpenROAD process...")
        result = await manager.stop_process()

        if result.status in ["stopped", "already_stopped"]:
            logger.info("OpenROAD process shutdown completed successfully")
        else:
            logger.warning(f"OpenROAD shutdown warning: {result.message}")
    except Exception as e:
        logger.error(f"Error during OpenROAD shutdown: {e}")


async def run_server(config: CLIConfig) -> None:
    """Main server entry point with lifecycle management."""
    logger.info(f"Starting OpenROAD MCP server in {config.transport.mode} mode...")

    try:
        # Register cleanup handlers
        cleanup_manager.register_async_cleanup_handler(shutdown_openroad)
        cleanup_manager.setup_signal_handlers()

        # Start OpenROAD process automatically
        await startup_openroad()

        # Run the MCP server with the configured transport
        if config.transport.mode == "stdio":
            logger.info("Using stdio transport")
            await mcp.run_async(transport="stdio")
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

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error in server: {e}")
        raise
    finally:
        # Ensure cleanup happens
        await shutdown_openroad()
        logger.info("OpenROAD MCP server shutdown complete")
