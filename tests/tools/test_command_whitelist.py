"""Tests for the command whitelist security feature."""

from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.config.command_whitelist import (
    BLOCKED_COMMANDS,
    _extract_verb,
    is_command_allowed,
)
from openroad_mcp.tools.interactive import InteractiveShellTool

# ── _extract_verb ─────────────────────────────────────────────────────────────


class TestExtractVerb:
    def test_simple_command(self):
        assert _extract_verb("report_checks") == "report_checks"

    def test_command_with_args(self):
        assert _extract_verb("report_checks -path_delay max") == "report_checks"

    def test_leading_whitespace(self):
        assert _extract_verb("   get_nets  *") == "get_nets"

    def test_empty_string(self):
        assert _extract_verb("") is None

    def test_blank_whitespace(self):
        assert _extract_verb("   ") is None

    def test_comment_line(self):
        assert _extract_verb("# this is a comment") is None

    def test_comment_with_leading_whitespace(self):
        assert _extract_verb("  # comment") is None

    def test_dollar_substitution(self):
        assert _extract_verb("$variable") is None

    def test_bracket_expression(self):
        assert _extract_verb("[report_wns]") is None

    def test_trailing_semicolon(self):
        assert _extract_verb("puts;") == "puts"


# ── is_command_allowed ────────────────────────────────────────────────────────


class TestIsCommandAllowed:
    # Allowed OpenROAD commands
    def test_report_checks_allowed(self):
        assert is_command_allowed("report_checks -path_delay max") == (True, None)

    def test_report_wns_allowed(self):
        assert is_command_allowed("report_wns") == (True, None)

    def test_get_nets_allowed(self):
        assert is_command_allowed("get_nets *") == (True, None)

    def test_read_db_allowed(self):
        assert is_command_allowed("read_db /path/to/design.odb") == (True, None)

    def test_write_db_allowed(self):
        assert is_command_allowed("write_db /out/design.odb") == (True, None)

    def test_read_sdc_allowed(self):
        assert is_command_allowed("read_sdc constraints.sdc") == (True, None)

    def test_set_clock_period_allowed(self):
        assert is_command_allowed("set_clock_period -name clk 2.0") == (True, None)

    def test_create_clock_allowed(self):
        assert is_command_allowed("create_clock -name clk -period 2.0 [get_ports clk]") == (True, None)

    def test_flow_command_allowed(self):
        assert is_command_allowed("global_placement") == (True, None)

    # Allowed Tcl built-ins
    def test_puts_allowed(self):
        assert is_command_allowed("puts hello") == (True, None)

    def test_set_variable_allowed(self):
        assert is_command_allowed("set x 42") == (True, None)

    def test_if_allowed(self):
        assert is_command_allowed("if {$x > 0} { puts positive }") == (True, None)

    def test_foreach_allowed(self):
        assert is_command_allowed("foreach net [get_nets *] { puts $net }") == (True, None)

    def test_comment_allowed(self):
        assert is_command_allowed("# this is a comment") == (True, None)

    def test_empty_command_allowed(self):
        assert is_command_allowed("") == (True, None)

    def test_whitespace_only_allowed(self):
        assert is_command_allowed("   \n   ") == (True, None)

    # Blocked commands
    def test_exec_blocked(self):
        allowed, verb = is_command_allowed("exec ls -la")
        assert allowed is False
        assert verb == "exec"

    def test_source_blocked(self):
        allowed, verb = is_command_allowed("source /tmp/malicious.tcl")
        assert allowed is False
        assert verb == "source"

    def test_exit_blocked(self):
        allowed, verb = is_command_allowed("exit")
        assert allowed is False
        assert verb == "exit"

    def test_quit_blocked(self):
        allowed, verb = is_command_allowed("quit")
        assert allowed is False
        assert verb == "quit"

    def test_open_blocked(self):
        allowed, verb = is_command_allowed("open /etc/passwd r")
        assert allowed is False
        assert verb == "open"

    def test_file_blocked(self):
        allowed, verb = is_command_allowed("file delete important.odb")
        assert allowed is False
        assert verb == "file"

    def test_socket_blocked(self):
        allowed, verb = is_command_allowed("socket -server handler 8080")
        assert allowed is False
        assert verb == "socket"

    def test_cd_blocked(self):
        allowed, verb = is_command_allowed("cd /tmp")
        assert allowed is False
        assert verb == "cd"

    def test_load_blocked(self):
        allowed, verb = is_command_allowed("load libevil.so")
        assert allowed is False
        assert verb == "load"

    # Unknown commands not in whitelist
    def test_unknown_command_blocked(self):
        allowed, verb = is_command_allowed("rm -rf /")
        assert allowed is False
        assert verb == "rm"

    def test_unknown_command_blocked_2(self):
        allowed, verb = is_command_allowed("curl http://evil.com")
        assert allowed is False
        assert verb == "curl"

    # Multi-statement inputs
    def test_multi_statement_all_allowed(self):
        cmd = "set x 1; report_wns; puts $x"
        assert is_command_allowed(cmd) == (True, None)

    def test_multi_statement_one_blocked(self):
        cmd = "report_wns; exec rm -rf /"
        allowed, verb = is_command_allowed(cmd)
        assert allowed is False
        assert verb == "exec"

    def test_multiline_all_allowed(self):
        cmd = "report_checks -path_delay max\nreport_wns\nreport_tns"
        assert is_command_allowed(cmd) == (True, None)

    def test_multiline_one_blocked(self):
        cmd = "report_checks\nsource /tmp/evil.tcl\nreport_wns"
        allowed, verb = is_command_allowed(cmd)
        assert allowed is False
        assert verb == "source"

    # Blocklist takes priority over patterns
    def test_blocklist_takes_priority_over_patterns(self):
        """exec must be blocked even though it doesn't match any pattern."""
        assert "exec" in BLOCKED_COMMANDS
        allowed, verb = is_command_allowed("exec openroad -no_init")
        assert allowed is False
        assert verb == "exec"


# ── InteractiveShellTool permission model ─────────────────────────────────────


@pytest.mark.asyncio
class TestInteractiveShellToolWhitelist:
    @pytest.fixture
    def mock_manager(self):
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager):
        return InteractiveShellTool(mock_manager)

    async def test_allowed_command_passes_through(self, tool, mock_manager):
        from openroad_mcp.core.models import InteractiveExecResult

        mock_manager.execute_command.return_value = InteractiveExecResult(
            output="wns = -0.1",
            session_id="s1",
            timestamp="2024-01-01T00:00:00",
            execution_time=0.05,
            command_count=1,
        )
        result = await tool.execute("report_wns", session_id="s1")
        mock_manager.execute_command.assert_called_once()
        assert "wns" in result

    async def test_risky_command_returns_permission_request(self, tool, mock_manager):
        """Dangerous commands must return a permission request, not execute."""
        result = await tool.execute("exec ls -la", session_id="s1")
        # Manager must NOT have been called
        mock_manager.execute_command.assert_not_called()
        assert "Permission required" in result
        assert "exec" in result
        assert "confirmed=True" in result
        assert "ConfirmationRequired" in result

    async def test_permission_request_includes_risk_reason(self, tool, mock_manager):
        result = await tool.execute("source /tmp/script.tcl", session_id="s1")
        assert "Permission required" in result
        assert "source" in result
        assert "Tcl script" in result  # reason text
        mock_manager.execute_command.assert_not_called()

    async def test_unknown_command_returns_permission_request(self, tool, mock_manager):
        """Commands not in the whitelist also require confirmation."""
        result = await tool.execute("rm -rf /important", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "Permission required" in result
        assert "rm" in result

    async def test_confirmed_true_executes_risky_command(self, tool, mock_manager):
        """confirmed=True bypasses the whitelist and executes."""
        from openroad_mcp.core.models import InteractiveExecResult

        mock_manager.execute_command.return_value = InteractiveExecResult(
            output="done",
            session_id="s1",
            timestamp="2024-01-01T00:00:00",
            execution_time=0.01,
            command_count=1,
        )
        result = await tool.execute("exec ls", session_id="s1", confirmed=True)
        mock_manager.execute_command.assert_called_once()
        assert "done" in result

    async def test_confirmed_true_not_needed_for_safe_commands(self, tool, mock_manager):
        """Safe commands execute without confirmed=True."""
        from openroad_mcp.core.models import InteractiveExecResult

        mock_manager.execute_command.return_value = InteractiveExecResult(
            output="area = 100",
            session_id="s1",
            timestamp="2024-01-01T00:00:00",
            execution_time=0.02,
            command_count=1,
        )
        result = await tool.execute("report_design_area", session_id="s1", confirmed=False)
        mock_manager.execute_command.assert_called_once()
        assert "area" in result

    async def test_whitelist_disabled_skips_permission_check(self, tool, mock_manager):
        """When WHITELIST_ENABLED=False dangerous commands go straight through."""
        from openroad_mcp.core.models import InteractiveExecResult

        mock_manager.execute_command.return_value = InteractiveExecResult(
            output="ok",
            session_id="s1",
            timestamp="2024-01-01T00:00:00",
            execution_time=0.01,
            command_count=1,
        )
        with patch("openroad_mcp.tools.interactive.settings") as mock_settings:
            mock_settings.WHITELIST_ENABLED = False
            result = await tool.execute("exec ls", session_id="s1")
            mock_manager.execute_command.assert_called_once()
            assert "ok" in result
