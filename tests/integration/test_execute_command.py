"""Integration tests for execute_openroad_command tool."""

import pytest
from mcp import ClientSession
from mcp.types import TextContent


class TestExecuteOpenROADCommand:
    """Integration tests for the execute_openroad_command tool."""

    @pytest.mark.asyncio
    async def test_execute_openroad_command(self, mcp_client: ClientSession):
        """Test that execute_openroad_command produces some output in stdout."""
        response = await mcp_client.call_tool(
            name="execute_openroad_command",
            arguments={
                "command": "help",
                "timeout": 5.0,
            },
        )

        assert response is not None
        assert hasattr(response, "content")
        assert len(response.content) > 0

        # Get the text content from the response
        text_content = None
        for content_item in response.content:
            if isinstance(content_item, TextContent):
                text_content = content_item.text
                break

        # Verify we have some text output
        assert text_content is not None
        assert len(text_content.strip()) > 0

        # Basic sanity check that it looks like command output
        assert isinstance(text_content, str)
