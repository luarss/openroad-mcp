"""Unit tests for TimingSession"""

from unittest.mock import AsyncMock, Mock

import pytest

from openroad_mcp.core.models import InteractiveExecResult
from openroad_mcp.timing.session import TimingSession


@pytest.fixture
async def mock_interactive_session():
    """Create mock interactive session"""
    session = AsyncMock()
    session.session_id = "test-session"
    session.send_command = AsyncMock()
    session.read_output = AsyncMock()
    return session


@pytest.fixture
async def timing_session(mock_interactive_session):
    """Create timing session with mock"""
    return TimingSession("timing-1", mock_interactive_session)


class TestODBLoading:
    """Test ODB file loading"""

    @pytest.mark.asyncio
    async def test_load_odb_file_not_found(self, timing_session):
        result = await timing_session.load_odb("/nonexistent/file.odb")
        assert not result.success
        assert "not found" in result.message.lower() or "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_load_odb_success(self, timing_session, tmp_path):
        odb_file = tmp_path / "test.odb"
        odb_file.touch()

        timing_session.session.read_output.return_value = InteractiveExecResult(
            output="Database read successfully",
            session_id="test",
            timestamp="2025-01-01",
            execution_time=0.1,
        )

        result = await timing_session.load_odb(odb_file)

        assert result.success
        assert result.design_name == "test"
        assert timing_session.design_name == "test"
        assert timing_session.session.send_command.called

    @pytest.mark.asyncio
    async def test_load_odb_with_sdc(self, timing_session, tmp_path):
        odb_file = tmp_path / "test.odb"
        sdc_file = tmp_path / "test.sdc"
        odb_file.touch()
        sdc_file.touch()

        timing_session.session.read_output.return_value = InteractiveExecResult(
            output="Success", session_id="test", timestamp="2025-01-01", execution_time=0.1
        )

        result = await timing_session.load_odb(odb_file, sdc_file)

        assert result.success
        assert timing_session.session.send_command.call_count == 2


class TestCommandExecution:
    """Test STA command execution"""

    @pytest.mark.asyncio
    async def test_execute_without_loaded_design(self, timing_session):
        result = await timing_session.execute_sta_command("report_wns")
        assert result.error is not None
        assert "no design loaded" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_caching(self, timing_session):
        timing_session.design_name = "test"

        timing_session.session.read_output.return_value = InteractiveExecResult(
            output="wns 2.45", session_id="test", timestamp="2025-01-01", execution_time=0.5
        )

        result1 = await timing_session.execute_sta_command("report_wns")
        assert not result1.cached
        assert result1.data["value"] == 2.45

        result2 = await timing_session.execute_sta_command("report_wns")
        assert result2.cached
        assert result2.data["value"] == 2.45

    @pytest.mark.asyncio
    async def test_execute_report_checks(self, timing_session):
        timing_session.design_name = "test"

        timing_session.session.read_output.return_value = InteractiveExecResult(
            output="""Startpoint: _692_
Endpoint: _693_
Path Group: clk
            2.10   slack (MET)
""",
            session_id="test",
            timestamp="2025-01-01",
            execution_time=0.5,
        )

        result = await timing_session.execute_sta_command("report_checks")
        assert not result.error
        assert "paths" in result.data
        assert result.data["path_count"] == 1


class TestCaching:
    """Test cache functionality"""

    @pytest.mark.asyncio
    async def test_clear_cache(self, timing_session):
        timing_session._cache["key1"] = Mock()
        timing_session._cache["key2"] = Mock()

        timing_session.clear_cache()

        assert len(timing_session._cache) == 0

    @pytest.mark.asyncio
    async def test_cache_bypass(self, timing_session):
        timing_session.design_name = "test"

        timing_session.session.read_output.return_value = InteractiveExecResult(
            output="wns 2.45", session_id="test", timestamp="2025-01-01", execution_time=0.5
        )

        await timing_session.execute_sta_command("report_wns", use_cache=True)

        await timing_session.execute_sta_command("report_wns", use_cache=False)

        assert timing_session.session.send_command.call_count == 2


class TestTimingSummary:
    """Test timing summary generation"""

    @pytest.mark.asyncio
    async def test_get_summary_no_design(self, timing_session):
        summary = await timing_session.get_summary()
        assert summary.design_name == "No design loaded"
        assert summary.wns is None
        assert summary.tns is None

    @pytest.mark.asyncio
    async def test_get_summary_with_design(self, timing_session):
        timing_session.design_name = "test"

        async def mock_read_output(*args, **kwargs):
            if "wns" in timing_session.session.send_command.call_args[0][0]:
                return InteractiveExecResult(
                    output="wns 2.45", session_id="test", timestamp="2025-01-01", execution_time=0.1
                )
            else:
                return InteractiveExecResult(
                    output="tns -10.5", session_id="test", timestamp="2025-01-01", execution_time=0.1
                )

        timing_session.session.read_output.side_effect = mock_read_output

        summary = await timing_session.get_summary()
        assert summary.design_name == "test"
        assert summary.wns == 2.45
        assert summary.tns == -10.5
