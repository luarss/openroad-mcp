"""Tests for Code Mode MCP tools."""

import json

import pytest

from openroad_mcp.code_mode.models import CodeExecuteResult, CodeSearchResult
from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.tools.code_mode import CodeExecuteTool, CodeSearchTool


class TestCodeSearchTool:
    """Tests for the CodeSearchTool class."""

    @pytest.fixture
    def tool(self) -> CodeSearchTool:
        """Create a tool instance."""
        manager = OpenROADManager()
        return CodeSearchTool(manager)

    def test_tool_initialization(self, tool: CodeSearchTool) -> None:
        """Test tool initializes correctly."""
        assert tool.manager is not None
        assert tool.executor is not None

    @pytest.mark.asyncio
    async def test_execute_returns_json(self, tool: CodeSearchTool) -> None:
        """Test that execute returns valid JSON."""
        result = await tool.execute("timing")

        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_execute_has_required_fields(self, tool: CodeSearchTool) -> None:
        """Test that result has required fields."""
        result = await tool.execute("sta")
        parsed = json.loads(result)

        assert "commands" in parsed
        assert "categories" in parsed
        assert "total_matches" in parsed
        assert "query" in parsed
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_execute_empty_query(self, tool: CodeSearchTool) -> None:
        """Test search with empty query."""
        result = await tool.execute("")
        parsed = json.loads(result)

        assert parsed["query"] == ""
        assert parsed["total_matches"] == 0


class TestCodeExecuteTool:
    """Tests for the CodeExecuteTool class."""

    @pytest.fixture
    def tool(self) -> CodeExecuteTool:
        """Create a tool instance."""
        manager = OpenROADManager()
        return CodeExecuteTool(manager)

    def test_tool_initialization(self, tool: CodeExecuteTool) -> None:
        """Test tool initializes correctly."""
        assert tool.manager is not None
        assert tool.executor is not None

    @pytest.mark.asyncio
    async def test_execute_returns_json(self, tool: CodeExecuteTool) -> None:
        """Test that execute returns valid JSON."""
        result = await tool.execute("puts hello")

        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_execute_has_required_fields(self, tool: CodeExecuteTool) -> None:
        """Test that result has required fields."""
        result = await tool.execute("puts hello")
        parsed = json.loads(result)

        assert "output" in parsed
        assert "session_id" in parsed
        assert "timestamp" in parsed
        assert "execution_time" in parsed
        assert "command_count" in parsed
        assert "confirmation_required" in parsed
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_execute_empty_code(self, tool: CodeExecuteTool) -> None:
        """Test execute with empty code."""
        result = await tool.execute("")
        parsed = json.loads(result)

        assert parsed["error"] == "Empty code"

    @pytest.mark.asyncio
    async def test_execute_blocked_code(self, tool: CodeExecuteTool) -> None:
        """Test execute with blocked code."""
        result = await tool.execute("exec ls", confirmed=False)
        parsed = json.loads(result)

        assert parsed["confirmation_required"] is True

    @pytest.mark.asyncio
    async def test_execute_with_session_id(self, tool: CodeExecuteTool) -> None:
        """Test execute with explicit session ID."""
        result = await tool.execute("puts hello", session_id="test_session")
        parsed = json.loads(result)

        # Session ID should be returned (session may or may not exist)
        assert "session_id" in parsed


class TestToolResultModels:
    """Tests for tool result model serialization."""

    def test_search_result_serialization(self) -> None:
        """Test CodeSearchResult serialization."""
        result = CodeSearchResult(
            commands=[],
            categories=["timing", "routing"],
            total_matches=0,
            query="test",
            error=None,
        )

        serialized = result.model_dump()
        assert serialized["query"] == "test"
        assert serialized["total_matches"] == 0
        assert len(serialized["categories"]) == 2

    def test_execute_result_serialization(self) -> None:
        """Test CodeExecuteResult serialization."""
        result = CodeExecuteResult(
            output="test output",
            session_id="test123",
            timestamp="2024-01-01T00:00:00",
            execution_time=1.5,
            command_count=3,
            confirmation_required=False,
            confirmation_reason=None,
            error=None,
        )

        serialized = result.model_dump()
        assert serialized["output"] == "test output"
        assert serialized["session_id"] == "test123"
        assert serialized["execution_time"] == 1.5
        assert serialized["command_count"] == 3
