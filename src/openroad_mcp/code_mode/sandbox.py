"""Sandbox validation for Code Mode multi-statement Tcl code."""

from ..config.command_whitelist import BLOCKED_COMMANDS, is_command_allowed
from ..utils.logging import get_logger

logger = get_logger("code_mode_sandbox")


class CodeSandbox:
    """Validates multi-statement Tcl code against the command whitelist."""

    def validate(self, code: str) -> tuple[bool, str | None]:
        """Validate all statements in the code against the whitelist.

        Args:
            code: Tcl code to validate (may contain multiple statements)

        Returns:
            Tuple of (is_valid, blocked_command_name). If is_valid is False,
            blocked_command_name contains the first blocked command.
        """
        if not code or not code.strip():
            return True, None

        # Reuse the existing is_command_allowed which handles multi-statement validation
        return is_command_allowed(code)

    def needs_confirmation(self, code: str) -> tuple[bool, str | None]:
        """Check if code contains commands that need user confirmation.

        Commands need confirmation if they:
        - Are in BLOCKED_COMMANDS (exec, source, exit, etc.)
        - Don't match any pattern in ALLOWED_PATTERNS

        Args:
            code: Tcl code to check

        Returns:
            Tuple of (needs_confirmation, reason). If needs_confirmation is True,
            reason contains a human-readable explanation.
        """
        if not code or not code.strip():
            return False, None

        allowed, blocked_verb = is_command_allowed(code)
        if allowed:
            return False, None

        # Determine the reason for blocking
        if blocked_verb:
            if blocked_verb in BLOCKED_COMMANDS:
                reason = f"Command '{blocked_verb}' is potentially dangerous and requires confirmation"
            else:
                reason = f"Command '{blocked_verb}' is not in the allowed command whitelist"

            logger.warning("Code needs confirmation: %s", reason)
            return True, reason

        return False, None

    def count_statements(self, code: str) -> int:
        """Count the number of Tcl statements in the code.

        This is a simple heuristic that counts non-empty, non-comment lines
        and semicolon-separated statements.

        Args:
            code: Tcl code

        Returns:
            Approximate number of statements
        """
        if not code or not code.strip():
            return 0

        count = 0
        for line in code.replace(";", "\n").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1

        return count
