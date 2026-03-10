"""Configuration for interactive tests."""

import gc

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def reset_manager_singleton():
    """Reset OpenROADManager singleton before and after each test."""
    from openroad_mcp.core.manager import OpenROADManager

    OpenROADManager._instance = None
    yield
    instance = OpenROADManager._instance
    if instance is not None:
        try:
            await instance.cleanup_all()
        except Exception:
            pass  # best-effort cleanup
    OpenROADManager._instance = None
    gc.collect()


# Configure pytest to run interactive tests with shorter timeouts
def pytest_configure(config):
    """Configure pytest for interactive tests."""
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add appropriate markers."""
    for item in items:
        # Mark PTY and session tests as potentially slow
        if "pty" in item.name.lower() or "session" in item.name.lower():
            item.add_marker(pytest.mark.slow)
