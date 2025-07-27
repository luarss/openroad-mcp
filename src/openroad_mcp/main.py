"""Main entry point for OpenROAD MCP server."""

import asyncio

from openroad_mcp.server import run_server
from openroad_mcp.utils.logging import setup_logging


def main() -> None:
    """Main application entry point."""
    # Setup logging
    setup_logging()

    # Run the server
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
