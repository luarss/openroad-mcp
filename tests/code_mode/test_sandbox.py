"""Tests for Code Mode sandbox validation."""

import pytest

from openroad_mcp.code_mode.sandbox import CodeSandbox


class TestCodeSandbox:
    """Tests for the CodeSandbox class."""

    @pytest.fixture
    def sandbox(self) -> CodeSandbox:
        """Create a sandbox instance."""
        return CodeSandbox()

    def test_validate_empty_code(self, sandbox: CodeSandbox) -> None:
        """Test validation of empty code."""
        valid, blocked = sandbox.validate("")
        assert valid is True
        assert blocked is None

        valid, blocked = sandbox.validate("   ")
        assert valid is True
        assert blocked is None

    def test_validate_safe_command(self, sandbox: CodeSandbox) -> None:
        """Test validation of safe commands."""
        valid, blocked = sandbox.validate("puts hello")
        assert valid is True
        assert blocked is None

        valid, blocked = sandbox.validate("report_timing")
        assert valid is True
        assert blocked is None

    def test_validate_blocked_command(self, sandbox: CodeSandbox) -> None:
        """Test validation of blocked commands."""
        valid, blocked = sandbox.validate("exec ls")
        assert valid is False
        assert blocked == "exec"

        valid, blocked = sandbox.validate("source script.tcl")
        assert valid is False
        assert blocked == "source"

    def test_validate_multiline_safe(self, sandbox: CodeSandbox) -> None:
        """Test validation of multi-line safe code."""
        code = """
# Run timing analysis
sta

# Report worst path
report_timing -max_paths 1
"""
        valid, blocked = sandbox.validate(code)
        assert valid is True
        assert blocked is None

    def test_validate_multiline_with_blocked(self, sandbox: CodeSandbox) -> None:
        """Test validation of multi-line code with blocked command."""
        code = """
puts "Starting"
exec ls
puts "Done"
"""
        valid, blocked = sandbox.validate(code)
        assert valid is False
        assert blocked == "exec"

    def test_needs_confirmation_safe(self, sandbox: CodeSandbox) -> None:
        """Test that safe code doesn't need confirmation."""
        needs, reason = sandbox.needs_confirmation("puts hello")
        assert needs is False
        assert reason is None

        needs, reason = sandbox.needs_confirmation("report_timing")
        assert needs is False
        assert reason is None

    def test_needs_confirmation_blocked(self, sandbox: CodeSandbox) -> None:
        """Test that blocked code needs confirmation."""
        needs, reason = sandbox.needs_confirmation("exec ls")
        assert needs is True
        assert reason is not None
        assert "exec" in reason.lower() or "dangerous" in reason.lower()

    def test_needs_confirmation_unknown(self, sandbox: CodeSandbox) -> None:
        """Test that unknown commands need confirmation."""
        needs, reason = sandbox.needs_confirmation("unknown_command_xyz")
        assert needs is True
        assert reason is not None

    def test_count_statements_empty(self, sandbox: CodeSandbox) -> None:
        """Test statement counting for empty code."""
        assert sandbox.count_statements("") == 0
        assert sandbox.count_statements("   ") == 0

    def test_count_statements_single(self, sandbox: CodeSandbox) -> None:
        """Test statement counting for single statement."""
        assert sandbox.count_statements("puts hello") == 1

    def test_count_statements_multiple_lines(self, sandbox: CodeSandbox) -> None:
        """Test statement counting for multiple lines."""
        code = """puts hello
puts world
puts test"""
        assert sandbox.count_statements(code) == 3

    def test_count_statements_with_semicolons(self, sandbox: CodeSandbox) -> None:
        """Test statement counting with semicolon separators."""
        code = "puts hello; puts world; puts test"
        assert sandbox.count_statements(code) == 3

    def test_count_statements_ignores_comments(self, sandbox: CodeSandbox) -> None:
        """Test that comments are not counted."""
        code = """# This is a comment
puts hello
# Another comment"""
        assert sandbox.count_statements(code) == 1

    def test_validate_set_allowed(self, sandbox: CodeSandbox) -> None:
        """Test that 'set' command is allowed (common Tcl command)."""
        valid, blocked = sandbox.validate("set my_var 42")
        assert valid is True
        assert blocked is None

    def test_validate_exit_blocked(self, sandbox: CodeSandbox) -> None:
        """Test that 'exit' command is blocked."""
        valid, blocked = sandbox.validate("exit")
        assert valid is False
        assert blocked == "exit"

    def test_validate_file_blocked(self, sandbox: CodeSandbox) -> None:
        """Test that 'file' command is blocked."""
        valid, blocked = sandbox.validate("file delete test.txt")
        assert valid is False
        assert blocked == "file"
