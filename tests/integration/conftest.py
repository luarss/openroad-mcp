"""Pytest configuration for integration tests without mocks."""

import asyncio
from collections.abc import AsyncGenerator

import pytest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest_asyncio.fixture(scope="function")
async def mcp_client() -> AsyncGenerator[ClientSession]:
    """Fixture providing a MCP client session."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "openroad_mcp.main"],
        env={
            "OPENROAD_ENABLE_COMMAND_VALIDATION": "false",
        },
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await asyncio.sleep(1.0)
                yield session
    except RuntimeError as e:
        # anyio emits a RuntimeError on cancel-scope teardown when the MCP
        # server subprocess exits
        if "cancel scope" in str(e).lower():
            pass
        else:
            raise
