"""Tests for Code Mode executor."""

import pytest

from openroad_mcp.code_mode.executor import CodeModeExecutor
from openroad_mcp.code_mode.registry import CommandRegistry, registry
from openroad_mcp.code_mode.sandbox import CodeSandbox
from openroad_mcp.core.manager import OpenROADManager


class TestCodeModeExecutor:
    """Tests for the CodeModeExecutor class."""

    @pytest.fixture
    def executor(self) -> CodeModeExecutor:
        """Create an executor instance."""
        manager = OpenROADManager()
        return CodeModeExecutor(manager, registry)

    def test_executor_initialization(self, executor: CodeModeExecutor) -> None:
        """Test executor initializes correctly."""
        assert executor.manager is not None
        assert executor.sandbox is not None
        assert executor.registry is not None

    def test_executor_has_sandbox(self, executor: CodeModeExecutor) -> None:
        """Test executor has sandbox instance."""
        assert isinstance(executor.sandbox, CodeSandbox)

    def test_executor_has_registry(self, executor: CodeModeExecutor) -> None:
        """Test executor has registry instance."""
        assert isinstance(executor.registry, CommandRegistry)

    @pytest.mark.asyncio
    async def test_search_empty_query(self, executor: CodeModeExecutor) -> None:
        """Test search with empty query."""
        result = await executor.search("")

        assert result["query"] == ""
        assert result["total_matches"] == 0
        assert result["commands"] == []
        assert result["categories"] is not None

    @pytest.mark.asyncio
    async def test_search_timing_query(self, executor: CodeModeExecutor) -> None:
        """Test search with timing query."""
        result = await executor.search("timing")

        assert result["query"] == "timing"
        assert result["total_matches"] >= 1
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_search_returns_categories(self, executor: CodeModeExecutor) -> None:
        """Test that search returns available categories."""
        result = await executor.search("sta")

        assert result["categories"] is not None
        assert len(result["categories"]) > 0

    @pytest.mark.asyncio
    async def test_execute_empty_code(self, executor: CodeModeExecutor) -> None:
        """Test execute with empty code."""
        result = await executor.execute("")

        assert result["error"] == "Empty code"
        assert result["output"] == "No code provided"
        assert result["command_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_blocked_code_needs_confirmation(self, executor: CodeModeExecutor) -> None:
        """Test that blocked code requires confirmation."""
        result = await executor.execute("exec ls", confirmed=False)

        assert result["confirmation_required"] is True
        assert result["confirmation_reason"] is not None
        assert result["execution_time"] == 0.0

    @pytest.mark.asyncio
    async def test_execute_safe_code_no_confirmation_needed(self, executor: CodeModeExecutor) -> None:
        """Test that safe code doesn't require confirmation."""
        result = await executor.execute("puts hello", confirmed=False)

        # Should not require confirmation (though execution may fail if no OpenROAD)
        assert result["confirmation_required"] is False

    def test_format_permission_request(self, executor: CodeModeExecutor) -> None:
        """Test permission request formatting."""
        msg = executor._format_permission_request("exec ls", "executes OS commands")

        assert "Permission required" in msg
        assert "exec" in msg.lower()
        assert "confirmed=True" in msg


class TestCodeModeExecutorIntegration:
    """Integration tests for CodeModeExecutor with OpenROADManager."""

    @pytest.fixture
    def manager(self) -> OpenROADManager:
        """Create a manager instance."""
        return OpenROADManager()

    @pytest.fixture
    def executor(self, manager: OpenROADManager) -> CodeModeExecutor:
        """Create an executor with manager."""
        return CodeModeExecutor(manager, registry)

    def test_executor_uses_provided_manager(self, manager: OpenROADManager) -> None:
        """Test executor uses the provided manager."""
        executor = CodeModeExecutor(manager)
        assert executor.manager is manager

    def test_executor_uses_custom_registry(self) -> None:
        """Test executor can use custom registry."""
        custom_registry = CommandRegistry()
        executor = CodeModeExecutor(OpenROADManager(), custom_registry)

        assert executor.registry is custom_registry
