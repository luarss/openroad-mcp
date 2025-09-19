"""Tests for SessionManager implementation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.core.models import SessionState
from openroad_mcp.interactive.models import SessionNotFoundError, SessionTerminatedError
from openroad_mcp.interactive.session_manager import SessionManager


class TestSessionManager:
    """Test suite for SessionManager."""

    @pytest.fixture
    def session_manager(self):
        """Create a test session manager."""
        return SessionManager()

    async def test_session_manager_initialization(self, session_manager):
        """Test session manager initialization."""
        assert len(session_manager.sessions) == 0
        assert session_manager.session_counter == 0

    async def test_create_session_default(self, session_manager):
        """Test creating session with default parameters."""
        session_id = await session_manager.create_session()

        assert session_id.startswith("session-")
        assert len(session_manager.sessions) == 1
        assert session_id in session_manager.sessions

        session = session_manager.sessions[session_id]
        assert session.session_id == session_id
        assert session.state == SessionState.CREATING

    async def test_create_session_with_params(self, session_manager):
        """Test creating session with custom parameters."""
        session_id = await session_manager.create_session(
            command=["echo", "test"], buffer_size=2048, env={"TEST": "value"}, cwd="/tmp"
        )

        session = session_manager.sessions[session_id]
        assert session.session_id == session_id

        # Session should be created but not started yet
        assert session.state == SessionState.CREATING

    async def test_get_session_info(self, session_manager):
        """Test getting session information."""
        session_id = await session_manager.create_session()

        info = await session_manager.get_session_info(session_id)
        assert info.session_id == session_id
        assert info.state == SessionState.CREATING
        assert info.command_count == 0

    async def test_get_session_info_not_found(self, session_manager):
        """Test getting info for non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.get_session_info("non-existent")

    async def test_list_sessions_empty(self, session_manager):
        """Test listing sessions when none exist."""
        result = await session_manager.list_sessions()

        assert result.session_count == 0
        assert len(result.sessions) == 0

    async def test_list_sessions_multiple(self, session_manager):
        """Test listing multiple sessions."""
        # Create multiple sessions
        session_ids = []
        for _i in range(3):
            session_id = await session_manager.create_session()
            session_ids.append(session_id)

        result = await session_manager.list_sessions()

        assert result.session_count == 3
        assert len(result.sessions) == 3

        returned_ids = [s.session_id for s in result.sessions]
        for session_id in session_ids:
            assert session_id in returned_ids

    @patch("openroad_mcp.interactive.session.InteractiveSession.start")
    async def test_execute_command_new_session(self, mock_start, session_manager):
        """Test executing command with automatic session creation."""
        mock_start.return_value = None

        # Mock the session's execute method
        with (
            patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
            patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
        ):
            mock_read.return_value = AsyncMock()
            mock_read.return_value.output = "test output"
            mock_read.return_value.session_id = "session-1"
            mock_read.return_value.execution_time = 0.1

            result = await session_manager.execute_command(session_id=None, command="test command", timeout_ms=1000)

            assert "test output" in result.output
            assert len(session_manager.sessions) == 1
            mock_start.assert_called_once()

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
            mock_terminate.assert_called_once_with(force=True)

    async def test_terminate_session_not_found(self, session_manager):
        """Test terminating non-existent session."""
        with pytest.raises(SessionNotFoundError):
            await session_manager.terminate_session("non-existent")

    async def test_cleanup_session(self, session_manager):
        """Test cleaning up a session."""
        session_id = await session_manager.create_session()

        with patch("openroad_mcp.interactive.session.InteractiveSession.cleanup") as mock_cleanup:
            await session_manager.cleanup_session(session_id)

            mock_cleanup.assert_called_once()
            assert session_id not in session_manager.sessions

    async def test_cleanup_session_not_found(self, session_manager):
        """Test cleaning up non-existent session."""
        # Should not raise exception, just ignore
        await session_manager.cleanup_session("non-existent")

    async def test_cleanup_all_sessions(self, session_manager):
        """Test cleaning up all sessions."""
        # Create multiple sessions
        session_ids = []
        for _i in range(3):
            session_id = await session_manager.create_session()
            session_ids.append(session_id)

        with patch("openroad_mcp.interactive.session.InteractiveSession.cleanup") as mock_cleanup:
            await session_manager.cleanup_all()

            assert mock_cleanup.call_count == 3
            assert len(session_manager.sessions) == 0

    async def test_session_auto_cleanup_on_error(self, session_manager):
        """Test that sessions are auto-cleaned on errors."""
        session_id = await session_manager.create_session()

        # Simulate session error
        session = session_manager.sessions[session_id]
        session.state = SessionState.ERROR

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
        assert len(session_manager.sessions) == 10

    async def test_session_counter_increment(self, session_manager):
        """Test that session counter increments correctly."""
        initial_counter = session_manager.session_counter

        session_id1 = await session_manager.create_session()
        assert session_manager.session_counter == initial_counter + 1

        session_id2 = await session_manager.create_session()
        assert session_manager.session_counter == initial_counter + 2

        # Session IDs should contain counter
        assert "1" in session_id1
        assert "2" in session_id2

    async def test_session_state_tracking(self, session_manager):
        """Test session state tracking through manager."""
        session_id = await session_manager.create_session()

        # Initially creating
        info = await session_manager.get_session_info(session_id)
        assert info.state == SessionState.CREATING

        # Change state and verify
        session = session_manager.sessions[session_id]
        session.state = SessionState.ACTIVE

        info = await session_manager.get_session_info(session_id)
        assert info.state == SessionState.ACTIVE

    async def test_session_command_history_tracking(self, session_manager):
        """Test command history tracking."""
        session_id = await session_manager.create_session()

        with (
            patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
            patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
        ):
            mock_read.return_value = AsyncMock()
            mock_read.return_value.output = "output"
            mock_read.return_value.session_id = session_id

            # Execute multiple commands
            await session_manager.execute_command(session_id, "cmd1")
            await session_manager.execute_command(session_id, "cmd2")

            # Verify command count increased
            info = await session_manager.get_session_info(session_id)
            assert info.command_count == 2


@pytest.mark.asyncio
class TestSessionManagerAsync:
    """Async test runner for SessionManager."""

    async def test_session_manager_lifecycle(self):
        """Test complete session manager lifecycle."""
        manager = SessionManager()

        try:
            # Create session
            session_id = await manager.create_session()
            assert len(manager.sessions) == 1

            # List sessions
            result = await manager.list_sessions()
            assert result.session_count == 1

            # Get session info
            info = await manager.get_session_info(session_id)
            assert info.session_id == session_id

            # Cleanup
            await manager.cleanup_session(session_id)
            assert len(manager.sessions) == 0

        finally:
            # Ensure cleanup
            await manager.cleanup_all()

    async def test_stress_session_operations(self):
        """Test stress operations on session manager."""
        manager = SessionManager()

        try:
            # Create many sessions rapidly
            tasks = []
            for _i in range(50):
                task = manager.create_session()
                tasks.append(task)

            session_ids = await asyncio.gather(*tasks)
            assert len(session_ids) == 50
            assert len(set(session_ids)) == 50  # All unique

            # List all sessions
            result = await manager.list_sessions()
            assert result.session_count == 50

            # Cleanup some sessions concurrently
            cleanup_tasks = []
            for i in range(0, 25):
                task = manager.cleanup_session(session_ids[i])
                cleanup_tasks.append(task)

            await asyncio.gather(*cleanup_tasks)
            assert len(manager.sessions) == 25

        finally:
            await manager.cleanup_all()
