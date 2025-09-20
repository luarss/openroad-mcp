#!/usr/bin/env python3
"""Standalone FastMCP server script for Claude Code integration.

This script provides a direct entry point for Claude Code to connect to the
OpenROAD MCP server using FastMCP with STDIO transport.

Usage with FastMCP:
    fastmcp install claude-code claude_code_server.py --python 3.13

Environment Variables:
    FASTMCP_MASK_ERROR_DETAILS=true    # Enable production error masking
    OPENROAD_RATE_LIMIT_PER_MIN=60     # Rate limit per minute
    OPENROAD_MAX_SESSIONS=10           # Maximum concurrent sessions
    OPENROAD_MAX_MEMORY_MB=500         # Memory limit in MB
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to Python path for imports
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Setup environment for production if not already set
if "FASTMCP_MASK_ERROR_DETAILS" not in os.environ:
    os.environ["FASTMCP_MASK_ERROR_DETAILS"] = "true"

if "OPENROAD_RATE_LIMIT_PER_MIN" not in os.environ:
    os.environ["OPENROAD_RATE_LIMIT_PER_MIN"] = "60"

if "OPENROAD_MAX_SESSIONS" not in os.environ:
    os.environ["OPENROAD_MAX_SESSIONS"] = "10"

if "OPENROAD_MAX_MEMORY_MB" not in os.environ:
    os.environ["OPENROAD_MAX_MEMORY_MB"] = "500"

# Import after path setup
from openroad_mcp.server import mcp, shutdown_openroad, startup_openroad  # noqa: E402
from openroad_mcp.utils.cleanup import cleanup_manager  # noqa: E402
from openroad_mcp.utils.logging import get_logger, setup_logging  # noqa: E402

# Setup logging for Claude Code integration
setup_logging(level="INFO")
logger = get_logger("claude_code_server")


async def main() -> None:
    """Main entry point for Claude Code integration."""
    logger.info("Starting OpenROAD MCP server for Claude Code...")

    try:
        # Register cleanup handlers
        cleanup_manager.register_async_cleanup_handler(shutdown_openroad)
        cleanup_manager.setup_signal_handlers()

        # Start OpenROAD process automatically
        await startup_openroad()

        # Run the FastMCP server with STDIO transport
        logger.info("Starting FastMCP server with STDIO transport for Claude Code")
        await mcp.run_async(transport="stdio")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception:
        logger.exception("Unexpected error in Claude Code server")
        raise
    finally:
        # Ensure cleanup happens
        await shutdown_openroad()
        logger.info("Claude Code MCP server shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
