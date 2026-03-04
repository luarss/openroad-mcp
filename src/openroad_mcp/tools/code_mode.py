"""Code Mode MCP tools for OpenROAD.

These tools provide a compact interface to OpenROAD's Tcl commands:
- code_search: Discover available commands
- code_execute: Execute Tcl code in a session
"""

import json

from ..code_mode.executor import CodeModeExecutor
from ..code_mode.models import CodeExecuteResult, CodeSearchResult
from ..code_mode.registry import registry
from ..core.manager import OpenROADManager
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("code_mode_tools")


class CodeSearchTool(BaseTool):
    """Tool for searching OpenROAD Tcl commands."""

    def __init__(self, manager: OpenROADManager) -> None:
        super().__init__(manager)
        self.executor = CodeModeExecutor(manager, registry)

    async def execute(self, query: str) -> str:
        """Search OpenROAD Tcl commands by name, category, or description.

        Args:
            query: Search query - can be a command name, category name,
                   or keyword to search in descriptions

        Returns:
            JSON string with search results including matching commands,
            their categories, and descriptions.
        """
        logger.debug("Code search query: %s", query)

        result_dict = await self.executor.search(query)
        result = CodeSearchResult(**result_dict)

        return json.dumps(result.model_dump(), indent=2, default=str)


class CodeExecuteTool(BaseTool):
    """Tool for executing Tcl code in OpenROAD sessions."""

    def __init__(self, manager: OpenROADManager) -> None:
        super().__init__(manager)
        self.executor = CodeModeExecutor(manager, registry)

    async def execute(
        self,
        code: str,
        session_id: str | None = None,
        confirmed: bool = False,
    ) -> str:
        """Execute Tcl code in an OpenROAD session.

        Multi-line Tcl scripts are supported. Commands are validated against
        the security whitelist. Dangerous commands require confirmed=True.

        Args:
            code: Tcl code to execute (can be multi-line)
            session_id: Optional session ID. If not provided, a new session
                       will be automatically created.
            confirmed: Set to True to confirm execution of flagged commands.
                      Required when code contains potentially dangerous commands.

        Returns:
            JSON string with execution results including output, session_id,
            execution time, and any errors.
        """
        logger.debug("Code execute: session=%s, confirmed=%s, code_len=%d", session_id, confirmed, len(code))

        result_dict = await self.executor.execute(code, session_id, confirmed)
        result = CodeExecuteResult(**result_dict)

        return json.dumps(result.model_dump(), indent=2, default=str)
