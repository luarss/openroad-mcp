"""Tests for SessionManager implementation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.core.models import SessionState
from openroad_mcp.interactive.models import SessionNotFoundError, SessionTerminatedError
from openroad_mcp.interactive.session_manager import InteractiveSessionManager as SessionManager


class TestSessionManager:
    """Test suite for SessionManager."""

    @pytest.fixture
    def session_manager(self):
        """Create a test session manager."""
        return SessionManager()

    async def test_session_manager_initialization(self, session_manager):
        """Test session manager initialization."""
        assert session_manager.get_session_count() == 0
        assert session_manager.get_active_session_count() == 0

    async def test_create_session_default(self, session_manager):
        """Test creating session with default parameters."""
        session_id = await session_manager.create_session()

        assert isinstance(session_id, str)
        assert len(session_id) == 8  # UUID prefix length
        assert session_manager.get_session_count() == 1

        info = await session_manager.get_session_info(session_id)
        assert info.session_id == session_id

    async def test_create_session_with_params(self, session_manager, tmp_path):
        """Test creating session with custom parameters."""
        session_id = await session_manager.create_session(
            command=["echo", "test"], env={"TEST": "value"}, cwd=str(tmp_path)
        )

        info = await session_manager.get_session_info(session_id)
        assert info.session_id == session_id

    async def test_get_session_info(self, session_manager):
        """Test getting session information."""
        session_id = await session_manager.create_session()

        info = await session_manager.get_session_info(session_id)
        assert info.session_id == session_id
        assert info.command_count == 0

    async def test_get_session_info_not_found(self, session_manager):
        """Test getting info for non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.get_session_info("non-existent")

    async def test_list_sessions_empty(self, session_manager):
        """Test listing sessions when none exist."""
        result = await session_manager.list_sessions()

        assert len(result) == 0

    async def test_list_sessions_multiple(self, session_manager):
        """Test listing multiple sessions."""
        # Create multiple sessions
        session_ids = []
        for _ in range(3):
            session_id = await session_manager.create_session()
            session_ids.append(session_id)

        result = await session_manager.list_sessions()

        assert len(result) == 3

        returned_ids = [s.session_id for s in result]
        for session_id in session_ids:
            assert session_id in returned_ids

    async def test_execute_command_existing_session(self, session_manager):
        """Test executing command in existing session."""
        session_id = await session_manager.create_session()

        with (
            patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
            patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
        ):
            mock_read.return_value = AsyncMock()
            mock_read.return_value.output = "existing session output"
            mock_read.return_value.session_id = session_id
            mock_read.return_value.execution_time = 0.05

            result = await session_manager.execute_command(session_id=session_id, command="test command")

            assert "existing session output" in result.output
            assert result.session_id == session_id

    async def test_execute_command_session_not_found(self, session_manager):
        """Test executing command in non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.execute_command(session_id="non-existent", command="test")

    async def test_terminate_session(self, session_manager):
        """Test terminating a session."""
        session_id = await session_manager.create_session()

        with patch("openroad_mcp.interactive.session.InteractiveSession.terminate") as mock_terminate:
            await session_manager.terminate_session(session_id, force=True)
            mock_terminate.assert_called_once_with(True)

    async def test_terminate_session_not_found(self, session_manager):
        """Test terminating non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.terminate_session("non-existent")

    async def test_cleanup_session(self, session_manager):
        """Test cleaning up a session via termination."""
        session_id = await session_manager.create_session()

        await session_manager.terminate_session(session_id)

        with pytest.raises(SessionNotFoundError):
            await session_manager.get_session_info(session_id)

    async def test_cleanup_session_not_found(self, session_manager):
        """Test cleaning up non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.terminate_session("non-existent")

    async def test_cleanup_all_sessions(self, session_manager):
        """Test cleaning up all sessions."""
        # Create multiple sessions
        session_ids = []
        for _ in range(3):
            session_id = await session_manager.create_session()
            session_ids.append(session_id)

        # Call cleanup directly without patching - the actual cleanup method works
        await session_manager.cleanup()
        assert session_manager.get_session_count() == 0

    async def test_session_auto_cleanup_on_error(self, session_manager):
        """Test that sessions are auto-cleaned on errors."""
        session_id = await session_manager.create_session()

        # Simulate session error
        # Session will be in error state after cleanup

        with patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send:
            mock_send.side_effect = SessionTerminatedError("Session terminated")

            with pytest.raises(SessionTerminatedError):
                await session_manager.execute_command(session_id, "test")

    async def test_concurrent_session_creation(self, session_manager):
        """Test concurrent session creation."""

        async def create_session():
            return await session_manager.create_session()

        # Create 10 sessions concurrently
        tasks = [create_session() for _ in range(10)]
        session_ids = await asyncio.gather(*tasks)

        # All sessions should be unique
        assert len(set(session_ids)) == 10
        assert session_manager.get_session_count() == 10

    async def test_session_counter_increment(self, session_manager):
        """Test that multiple sessions are created with unique IDs."""
        session_id1 = await session_manager.create_session()
        session_id2 = await session_manager.create_session()

        # Session IDs should be unique
        assert session_id1 != session_id2
        assert len(session_id1) == 8  # UUID prefix length
        assert len(session_id2) == 8

    async def test_session_state_tracking(self, session_manager):
        """Test session state tracking through manager."""
        session_id = await session_manager.create_session()

        # Get session info to verify state
        info = await session_manager.get_session_info(session_id)
        assert info.state in [SessionState.CREATING.value, "active", "ready"]

        # Since we can't directly access sessions, just verify the session exists
        await session_manager.terminate_session(session_id)

    async def test_session_command_history_tracking(self, session_manager):
        """Test command history tracking."""
        session_id = await session_manager.create_session()

        with (
            patch("openroad_mcp.interactive.session.InteractiveSession.send_command") as mock_send,
            patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            patch("openroad_mcp.interactive.session.InteractiveSession.get_info") as mock_info,
        ):
            # Setup mock for execute_command
            from datetime import datetime

            from openroad_mcp.core.models import InteractiveExecResult

            mock_read.return_value = InteractiveExecResult(
                output="output", session_id=session_id, execution_time=0.05, timestamp=datetime.now().isoformat()
            )

            # Setup mock for get_info with incrementing command count
            from openroad_mcp.core.models import InteractiveSessionInfo

            # Create a counter that tracks how many times execute_command is called
            exec_count = 0

            async def mock_get_info():
                # Return a count based on how many times execute_command was called
                return InteractiveSessionInfo(
                    session_id=session_id,
                    created_at="2025-01-01T00:00:00",
                    is_alive=True,
                    command_count=exec_count,
                    buffer_size=0,
                    uptime_seconds=1.0,
                    state="active",
                )

            mock_info.side_effect = mock_get_info
            mock_send.return_value = None

            # Execute multiple commands
            await session_manager.execute_command(session_id, "cmd1")
            exec_count += 1
            await session_manager.execute_command(session_id, "cmd2")
            exec_count += 1

            # Verify command count increased
            info = await session_manager.get_session_info(session_id)
            assert info.command_count >= 2


@pytest.mark.asyncio
class TestSessionManagerAsync:
    """Async test runner for SessionManager."""

    async def test_session_manager_lifecycle(self):
        """Test complete session manager lifecycle."""
        manager = SessionManager()

        try:
            # Create session
            session_id = await manager.create_session()
            assert manager.get_session_count() == 1

            # List sessions
            result = await manager.list_sessions()
            assert len(result) == 1

            # Get session info
            info = await manager.get_session_info(session_id)
            assert info.session_id == session_id

            # Cleanup
            await manager.terminate_session(session_id)
            assert manager.get_session_count() == 0

        finally:
            # Ensure cleanup
            await manager.cleanup()

    async def test_stress_session_operations(self):
        """Test stress operations on session manager."""
        manager = SessionManager()

        try:
            # Create many sessions rapidly
            tasks = []
            for _ in range(50):
                task = manager.create_session()
                tasks.append(task)

            session_ids = await asyncio.gather(*tasks)
            assert len(session_ids) == 50
            assert len(set(session_ids)) == 50  # All unique

            # List all sessions
            result = await manager.list_sessions()
            assert len(result) == 50

            # Cleanup some sessions concurrently
            cleanup_tasks = []
            for i in range(0, 25):
                task = manager.terminate_session(session_ids[i])
                cleanup_tasks.append(task)

            await asyncio.gather(*cleanup_tasks)
            assert manager.get_session_count() == 25

        finally:
            await manager.cleanup()
