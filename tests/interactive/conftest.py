"""Configuration for interactive tests."""

import pytest


@pytest.fixture(autouse=True)
async def setup_test_isolation():
    """Ensure proper test isolation for PTY operations."""
    # This fixture runs before each test to ensure clean state
    yield
    # Cleanup after each test
    # Force garbage collection to help with file descriptor cleanup
    import gc

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
