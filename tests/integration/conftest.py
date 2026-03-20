"""Pytest configuration for integration tests without mocks."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def _mcp_session(server_params: StdioServerParameters):
    """Shared async context manager for MCP client sessions with cancel-scope guard."""
    _in_teardown = False
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await asyncio.sleep(1.0)
                yield session
                # Yield returned normally; cleanup follows
                _in_teardown = True
    except RuntimeError as e:
        # anyio emits a RuntimeError on cancel-scope teardown when the MCP
        # server subprocess exits. Only suppress it during teardown, not if it
        # originated from the test body.
        if not _in_teardown or "cancel scope" not in str(e).lower():
            raise


@pytest_asyncio.fixture(scope="function")
async def mcp_client() -> AsyncGenerator[ClientSession]:
    """Fixture providing a MCP client session."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "openroad_mcp.main"],
        env={
            **os.environ,
            "OPENROAD_ENABLE_COMMAND_VALIDATION": "false",
        },
    )

    async with _mcp_session(server_params) as session:
        yield session
