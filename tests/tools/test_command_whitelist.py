"""Tests for the command whitelist security feature."""

from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.config.command_whitelist import (
    ALLOWED_PATTERNS,
    BLOCKED_COMMANDS,
    MODIFY_PATTERNS,
    READONLY_PATTERNS,
    _extract_verb,
    is_command_allowed,
    is_modify_command,
    is_readonly_command,
)
from openroad_mcp.tools.interactive import ExecShellTool, QueryShellTool

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


# ── Pattern set membership ────────────────────────────────────────────────────


class TestPatternSets:
    def test_readonly_contains_report(self):
        assert "report_*" in READONLY_PATTERNS

    def test_readonly_contains_get(self):
        assert "get_*" in READONLY_PATTERNS

    def test_readonly_contains_check(self):
        assert "check_*" in READONLY_PATTERNS

    def test_modify_contains_set(self):
        assert "set_*" in MODIFY_PATTERNS

    def test_modify_contains_read(self):
        assert "read_*" in MODIFY_PATTERNS

    def test_modify_contains_write(self):
        assert "write_*" in MODIFY_PATTERNS

    def test_modify_contains_flow_commands(self):
        assert "global_placement" in MODIFY_PATTERNS
        assert "detailed_route" in MODIFY_PATTERNS

    def test_tcl_builtins_in_both(self):
        assert "puts" in READONLY_PATTERNS
        assert "puts" in MODIFY_PATTERNS
        assert "foreach" in READONLY_PATTERNS
        assert "foreach" in MODIFY_PATTERNS

    def test_allowed_patterns_is_union(self):
        # Every readonly and modify pattern must appear in ALLOWED_PATTERNS
        for p in READONLY_PATTERNS:
            assert p in ALLOWED_PATTERNS
        for p in MODIFY_PATTERNS:
            assert p in ALLOWED_PATTERNS

    def test_report_not_in_modify(self):
        assert "report_*" not in MODIFY_PATTERNS

    def test_set_star_not_in_readonly(self):
        assert "set_*" not in READONLY_PATTERNS


# ── is_readonly_command ───────────────────────────────────────────────────────


class TestIsReadonlyCommand:
    def test_report_allowed(self):
        assert is_readonly_command("report_checks -path_delay max") == (True, None)

    def test_get_allowed(self):
        assert is_readonly_command("get_nets *") == (True, None)

    def test_check_allowed(self):
        assert is_readonly_command("check_placement") == (True, None)

    def test_sta_allowed(self):
        assert is_readonly_command("sta") == (True, None)

    def test_help_allowed(self):
        assert is_readonly_command("help") == (True, None)

    def test_puts_allowed(self):
        assert is_readonly_command("puts hello") == (True, None)

    def test_set_variable_allowed(self):
        # bare 'set' is Tcl variable assignment — allowed as a Tcl built-in
        assert is_readonly_command("set x 42") == (True, None)

    def test_set_star_blocked(self):
        # set_clock_period is a modifier — not in READONLY_PATTERNS
        allowed, verb = is_readonly_command("set_clock_period -name clk 2.0")
        assert allowed is False
        assert verb == "set_clock_period"

    def test_read_db_blocked(self):
        allowed, verb = is_readonly_command("read_db /path/to/design.odb")
        assert allowed is False
        assert verb == "read_db"

    def test_write_db_blocked(self):
        allowed, verb = is_readonly_command("write_db /out/design.odb")
        assert allowed is False
        assert verb == "write_db"

    def test_flow_command_blocked(self):
        allowed, verb = is_readonly_command("global_placement")
        assert allowed is False
        assert verb == "global_placement"

    def test_exec_blocked(self):
        allowed, verb = is_readonly_command("exec ls -la")
        assert allowed is False
        assert verb == "exec"

    def test_unknown_command_blocked(self):
        allowed, verb = is_readonly_command("rm -rf /")
        assert allowed is False
        assert verb == "rm"

    def test_comment_allowed(self):
        assert is_readonly_command("# comment") == (True, None)

    def test_empty_allowed(self):
        assert is_readonly_command("") == (True, None)

    def test_multiline_all_readonly(self):
        cmd = "report_checks\nreport_wns\nget_nets *"
        assert is_readonly_command(cmd) == (True, None)

    def test_multiline_mixed_blocked(self):
        cmd = "report_checks\nglobal_placement"
        allowed, verb = is_readonly_command(cmd)
        assert allowed is False
        assert verb == "global_placement"


# ── is_modify_command ─────────────────────────────────────────────────────────


class TestIsModifyCommand:
    def test_set_clock_period_allowed(self):
        assert is_modify_command("set_clock_period -name clk 2.0") == (True, None)

    def test_create_clock_allowed(self):
        assert is_modify_command("create_clock -name clk -period 2.0 [get_ports clk]") == (True, None)

    def test_read_db_allowed(self):
        assert is_modify_command("read_db /path/to/design.odb") == (True, None)

    def test_write_db_allowed(self):
        assert is_modify_command("write_db /out/design.odb") == (True, None)

    def test_flow_command_allowed(self):
        assert is_modify_command("global_placement") == (True, None)

    def test_puts_allowed(self):
        assert is_modify_command("puts hello") == (True, None)

    def test_foreach_allowed(self):
        assert is_modify_command("foreach net [get_nets *] { puts $net }") == (True, None)

    def test_report_blocked(self):
        # report_* is read-only — not in MODIFY_PATTERNS
        allowed, verb = is_modify_command("report_wns")
        assert allowed is False
        assert verb == "report_wns"

    def test_get_blocked(self):
        allowed, verb = is_modify_command("get_nets *")
        assert allowed is False
        assert verb == "get_nets"

    def test_exec_blocked(self):
        allowed, verb = is_modify_command("exec ls -la")
        assert allowed is False
        assert verb == "exec"

    def test_unknown_command_blocked(self):
        allowed, verb = is_modify_command("curl http://evil.com")
        assert allowed is False
        assert verb == "curl"

    def test_multiline_all_modify(self):
        cmd = "read_db design.odb\nglobal_placement\nwrite_db out.odb"
        assert is_modify_command(cmd) == (True, None)

    def test_multiline_mixed_blocked(self):
        cmd = "global_placement\nreport_wns"
        allowed, verb = is_modify_command(cmd)
        assert allowed is False
        assert verb == "report_wns"


# ── is_command_allowed (union, backward compat) ───────────────────────────────


class TestIsCommandAllowed:
    def test_report_checks_allowed(self):
        assert is_command_allowed("report_checks -path_delay max") == (True, None)

    def test_get_nets_allowed(self):
        assert is_command_allowed("get_nets *") == (True, None)

    def test_read_db_allowed(self):
        assert is_command_allowed("read_db /path/to/design.odb") == (True, None)

    def test_write_db_allowed(self):
        assert is_command_allowed("write_db /out/design.odb") == (True, None)

    def test_set_clock_period_allowed(self):
        assert is_command_allowed("set_clock_period -name clk 2.0") == (True, None)

    def test_create_clock_allowed(self):
        assert is_command_allowed("create_clock -name clk -period 2.0 [get_ports clk]") == (True, None)

    def test_flow_command_allowed(self):
        assert is_command_allowed("global_placement") == (True, None)

    def test_puts_allowed(self):
        assert is_command_allowed("puts hello") == (True, None)

    def test_set_variable_allowed(self):
        assert is_command_allowed("set x 42") == (True, None)

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

    def test_unknown_command_blocked(self):
        allowed, verb = is_command_allowed("rm -rf /")
        assert allowed is False
        assert verb == "rm"

    def test_multi_statement_all_allowed(self):
        cmd = "set x 1; report_wns; puts $x"
        assert is_command_allowed(cmd) == (True, None)

    def test_multi_statement_one_blocked(self):
        cmd = "report_wns; exec rm -rf /"
        allowed, verb = is_command_allowed(cmd)
        assert allowed is False
        assert verb == "exec"

    def test_blocklist_takes_priority(self):
        assert "exec" in BLOCKED_COMMANDS
        allowed, verb = is_command_allowed("exec openroad -no_init")
        assert allowed is False
        assert verb == "exec"


# ── QueryShellTool whitelist enforcement ──────────────────────────────────────


@pytest.mark.asyncio
class TestQueryShellToolWhitelist:
    @pytest.fixture
    def mock_manager(self):
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager):
        return QueryShellTool(mock_manager)

    async def test_readonly_command_executes(self, tool, mock_manager):
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

    async def test_modify_command_blocked(self, tool, mock_manager):
        result = await tool.execute("global_placement", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result
        assert "global_placement" in result

    async def test_blocked_command_hard_blocked(self, tool, mock_manager):
        result = await tool.execute("exec ls -la", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result
        assert "exec" in result

    async def test_unknown_command_blocked(self, tool, mock_manager):
        result = await tool.execute("rm -rf /", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result

    async def test_whitelist_disabled_skips_check(self, tool, mock_manager):
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


# ── ExecShellTool whitelist enforcement ───────────────────────────────────────


@pytest.mark.asyncio
class TestExecShellToolWhitelist:
    @pytest.fixture
    def mock_manager(self):
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager):
        return ExecShellTool(mock_manager)

    async def test_modify_command_executes(self, tool, mock_manager):
        from openroad_mcp.core.models import InteractiveExecResult

        mock_manager.execute_command.return_value = InteractiveExecResult(
            output="placement done",
            session_id="s1",
            timestamp="2024-01-01T00:00:00",
            execution_time=1.5,
            command_count=1,
        )
        result = await tool.execute("global_placement", session_id="s1")
        mock_manager.execute_command.assert_called_once()
        assert "placement" in result

    async def test_readonly_command_blocked(self, tool, mock_manager):
        result = await tool.execute("report_wns", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result
        assert "report_wns" in result

    async def test_blocked_command_hard_blocked(self, tool, mock_manager):
        result = await tool.execute("exec ls -la", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result
        assert "exec" in result

    async def test_unknown_command_blocked(self, tool, mock_manager):
        result = await tool.execute("curl http://evil.com", session_id="s1")
        mock_manager.execute_command.assert_not_called()
        assert "CommandBlocked" in result

    async def test_whitelist_disabled_skips_check(self, tool, mock_manager):
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
