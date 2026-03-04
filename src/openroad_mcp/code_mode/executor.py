"""Code Mode execution engine for OpenROAD."""

import json
import time
from datetime import datetime

from ..config.command_whitelist import BLOCKED_COMMANDS
from ..config.settings import settings
from ..core.manager import OpenROADManager
from ..interactive.models import SessionError, SessionNotFoundError
from ..utils.logging import get_logger
from .models import CodeExecuteResult, CodeSearchResult
from .registry import CommandRegistry, registry
from .sandbox import CodeSandbox

logger = get_logger("code_mode_executor")

# Risk reasons for blocked commands (shared with interactive tools)
_RISK_REASONS: dict[str, str] = {
    "exec": "executes arbitrary OS commands outside OpenROAD",
    "source": "loads and runs an arbitrary Tcl script from disk",
    "exit": "terminates the OpenROAD process and destroys the session",
    "quit": "terminates the OpenROAD process and destroys the session",
    "open": "opens raw file handles, bypassing OpenROAD I/O wrappers",
    "close": "closes file handles",
    "socket": "opens network connections",
    "load": "loads compiled C extensions into the interpreter",
    "file": "manipulates the filesystem (delete, rename, mkdir…)",
    "cd": "changes the working directory",
    "glob": "enumerates the filesystem",
    "fconfigure": "reconfigures I/O channels",
    "chan": "performs low-level channel operations",
    "vwait": "blocks the event loop",
    "rename": "renames or removes commands, bypassing top-level whitelist checks",
    "uplevel": "evaluates scripts in a different call-stack level",
    "after": "schedules arbitrary code for deferred execution",
    "subst": "performs substitutions that can invoke arbitrary commands",
}


class CodeModeExecutor:
    """Execution engine for Code Mode tools."""

    def __init__(self, manager: OpenROADManager, cmd_registry: CommandRegistry | None = None):
        """Initialize the Code Mode executor.

        Args:
            manager: OpenROAD manager instance for session management
            cmd_registry: Optional command registry (uses global by default)
        """
        self.manager = manager
        self.sandbox = CodeSandbox()
        self.registry = cmd_registry or registry

    async def search(self, query: str) -> dict:
        """Search command registry by name, category, or pattern.

        Args:
            query: Search query (command name, category, or keyword)

        Returns:
            Dictionary with search results suitable for CodeSearchResult
        """
        if not query or not query.strip():
            return {
                "commands": [],
                "categories": self.registry.get_categories(),
                "total_matches": 0,
                "query": query or "",
                "error": None,
            }

        try:
            commands = self.registry.search(query)
            categories = self.registry.get_categories()

            return {
                "commands": [cmd.model_dump() for cmd in commands],
                "categories": categories,
                "total_matches": len(commands),
                "query": query,
                "error": None,
            }

        except Exception as e:
            logger.exception("Search failed for query: %s", query)
            return {
                "commands": [],
                "categories": None,
                "total_matches": 0,
                "query": query,
                "error": f"Search failed: {str(e)}",
            }

    async def execute(
        self,
        code: str,
        session_id: str | None = None,
        confirmed: bool = False,
    ) -> dict:
        """Execute validated Tcl code in an OpenROAD session.

        Args:
            code: Tcl code to execute (may be multi-line)
            session_id: Optional session ID (auto-created if not provided)
            confirmed: Set True to confirm execution of flagged commands

        Returns:
            Dictionary with execution results suitable for CodeExecuteResult
        """
        start_time = time.time()
        timestamp = datetime.now().isoformat()

        # Handle empty code
        if not code or not code.strip():
            return {
                "output": "No code provided",
                "session_id": session_id,
                "timestamp": timestamp,
                "execution_time": 0.0,
                "command_count": 0,
                "confirmation_required": False,
                "confirmation_reason": None,
                "error": "Empty code",
            }

        # Check whitelist if enabled
        if settings.WHITELIST_ENABLED and not confirmed:
            needs_confirm, reason = self.sandbox.needs_confirmation(code)
            if needs_confirm:
                logger.warning("Code requires confirmation: %s", reason)
                return {
                    "output": self._format_permission_request(code, reason or "Unknown command"),
                    "session_id": session_id,
                    "timestamp": timestamp,
                    "execution_time": 0.0,
                    "command_count": 0,
                    "confirmation_required": True,
                    "confirmation_reason": reason,
                    "error": None,
                }

        # Log confirmed dangerous commands for audit
        if confirmed and settings.WHITELIST_ENABLED:
            _, blocked_verb = self.sandbox.validate(code)
            if blocked_verb:
                logger.warning("User confirmed execution of '%s' (audit)", blocked_verb)

        try:
            # Create or reuse session
            if session_id is None:
                session_id = await self.manager.create_session()

            # Count statements
            command_count = self.sandbox.count_statements(code)

            # Execute the code
            result = await self.manager.execute_command(session_id, code)

            execution_time = time.time() - start_time

            return {
                "output": result.output,
                "session_id": session_id,
                "timestamp": timestamp,
                "execution_time": execution_time,
                "command_count": command_count,
                "confirmation_required": False,
                "confirmation_reason": None,
                "error": result.error,
            }

        except SessionNotFoundError as e:
            logger.warning("Session not found: %s", session_id)
            return {
                "output": f"Error: Session '{session_id}' not found. Please check session ID or create a new session.",
                "session_id": session_id,
                "timestamp": timestamp,
                "execution_time": time.time() - start_time,
                "command_count": 0,
                "confirmation_required": False,
                "confirmation_reason": None,
                "error": str(e),
            }

        except SessionError as e:
            logger.error("Session error for %s: %s", session_id, e)
            return {
                "output": f"Session Error: {str(e)}. The session may have terminated or encountered an issue.",
                "session_id": session_id,
                "timestamp": timestamp,
                "execution_time": time.time() - start_time,
                "command_count": 0,
                "confirmation_required": False,
                "confirmation_reason": None,
                "error": str(e),
            }

        except Exception as e:
            logger.exception("Unexpected error executing code in session %s", session_id)
            return {
                "output": f"Unexpected error occurred: {str(e)}. Please try again or contact support.",
                "session_id": session_id,
                "timestamp": timestamp,
                "execution_time": time.time() - start_time,
                "command_count": 0,
                "confirmation_required": False,
                "confirmation_reason": None,
                "error": str(e),
            }

    def _format_permission_request(self, code: str, reason: str) -> str:
        """Format a permission request message for blocked code.

        Args:
            code: The blocked code
            reason: The reason for blocking

        Returns:
            Formatted permission request message
        """
        # Get first line for display
        first_line = code.strip().split("\n")[0][:80]
        if len(code.strip()) > 80:
            first_line += "..."

        # Determine risk label
        _, blocked_verb = self.sandbox.validate(code)
        if blocked_verb and blocked_verb in BLOCKED_COMMANDS:
            risk_label = "potentially dangerous"
            detail_reason = _RISK_REASONS.get(blocked_verb, reason)
        else:
            risk_label = "unrecognised"
            detail_reason = reason

        return (
            f"Permission required\n\n"
            f"Code contains {risk_label} command(s): {detail_reason}.\n"
            f"First statement: {first_line!r}\n\n"
            f"To proceed, call code_execute again with confirmed=True.\n"
            f"To cancel, do not call again."
        )

    def _format_search_result(self, result: CodeSearchResult) -> str:
        """Format search result as JSON string."""
        return json.dumps(result.model_dump(), indent=2, default=str)

    def _format_execute_result(self, result: CodeExecuteResult) -> str:
        """Format execute result as JSON string."""
        return json.dumps(result.model_dump(), indent=2, default=str)
