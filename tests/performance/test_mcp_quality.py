"""MCP quality benchmarks: token efficiency, task accuracy, description quality, latency."""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from openroad_mcp.core.models import (
    ErrorCode,
    InteractiveExecResult,
    InteractiveSessionListResult,
)
from openroad_mcp.tools.interactive import (
    InspectSessionTool,
    ListSessionsTool,
    SessionHistoryTool,
    TerminateSessionTool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(**kwargs) -> MagicMock:
    """Return a mock OpenROADManager with sensible defaults."""
    m = MagicMock()
    for attr, val in kwargs.items():
        setattr(m, attr, val)
    return m


def _token_estimate(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# 1. Token efficiency
# ---------------------------------------------------------------------------


class TestTokenEfficiency:
    """Assert that serialized results use compact JSON (no indent=2)."""

    def _exec_result_json(self) -> str:
        result = InteractiveExecResult(
            output="% ok",
            session_id="s1",
            timestamp=datetime.now().isoformat(),
            execution_time=0.01,
        )
        return json.dumps(result.model_dump(), separators=(",", ":"))

    def test_no_newlines_in_output(self):
        """Compact JSON must not contain newlines."""
        manager = _make_manager()
        tool = ListSessionsTool(manager)
        manager.list_sessions = AsyncMock(return_value=[])
        result = asyncio.run(tool.execute())
        assert "\n" not in result, "indent=2 still active — newline found in output"

    def test_no_double_spaces(self):
        """Compact JSON must not contain double spaces (artifact of pretty-printing)."""
        manager = _make_manager()
        tool = ListSessionsTool(manager)
        manager.list_sessions = AsyncMock(return_value=[])
        result = asyncio.run(tool.execute())
        assert "  " not in result, "double spaces found — output is not compact"

    def test_exec_result_token_budget(self):
        """A minimal InteractiveExecResult must fit in <80 tokens."""
        result = InteractiveExecResult(
            output="% ok",
            session_id="s1",
            timestamp="2026-01-01T00:00:00",
            execution_time=0.01,
        )
        import json as _json

        serialized = _json.dumps(result.model_dump(), separators=(",", ":"))
        tokens = _token_estimate(serialized)
        assert tokens < 80, f"Exec result uses {tokens} tokens, budget is 80"

    def test_session_list_empty_token_budget(self):
        """An empty session list result must fit in <30 tokens."""
        result = InteractiveSessionListResult(sessions=[], total_count=0, active_count=0)
        import json as _json

        serialized = _json.dumps(result.model_dump(), separators=(",", ":"))
        tokens = _token_estimate(serialized)
        assert tokens < 30, f"Empty session list uses {tokens} tokens, budget is 30"

    def test_compact_vs_indent2_savings(self):
        """Compact JSON must be smaller than indent=2 for a typical result."""
        import json as _json

        result = InteractiveExecResult(
            output="set x [expr 1+1]; puts $x",
            session_id="test-session-abc123",
            timestamp="2026-01-01T12:34:56.789000",
            execution_time=0.123,
            command_count=5,
            buffer_size=1024,
        )
        data = result.model_dump()
        compact = len(_json.dumps(data, separators=(",", ":")))
        pretty = len(_json.dumps(data, indent=2))
        savings_pct = (pretty - compact) / pretty * 100
        assert savings_pct >= 10, f"Only {savings_pct:.1f}% savings vs indent=2, expected ≥10%"


# ---------------------------------------------------------------------------
# 2. Task accuracy
# ---------------------------------------------------------------------------


class TestTaskAccuracy:
    """Verify that tool outputs contain correct, parseable fields for common scenarios."""

    def test_session_list_count_matches_sessions(self):
        """total_count must equal len(sessions) in the response."""
        manager = _make_manager()
        session_info = MagicMock()
        session_info.is_alive = True
        session_info.model_dump = MagicMock(
            return_value={
                "session_id": "s1",
                "created_at": "2026-01-01T00:00:00",
                "is_alive": True,
                "command_count": 0,
                "buffer_size": 0,
                "uptime_seconds": 1.0,
                "state": "active",
                "error": None,
                "error_code": None,
            }
        )
        manager.list_sessions = AsyncMock(return_value=[session_info])
        tool = ListSessionsTool(manager)
        raw = asyncio.run(tool.execute())
        data = json.loads(raw)
        assert data["total_count"] == len(data["sessions"]), "total_count must equal len(sessions)"

    def test_exec_result_contains_output_field(self):
        """Every exec result must have an 'output' key."""
        manager = _make_manager()
        exec_result = InteractiveExecResult(
            output="2",
            session_id="s1",
            timestamp=datetime.now().isoformat(),
            execution_time=0.05,
        )
        manager.execute_command = AsyncMock(return_value=exec_result)
        manager.create_session = AsyncMock(return_value="s1")
        from openroad_mcp.tools.interactive import InteractiveShellTool

        tool = InteractiveShellTool(manager)
        raw = asyncio.run(tool.execute("puts 2", session_id="s1"))
        data = json.loads(raw)
        assert "output" in data, "exec result must contain 'output' field"

    def test_not_found_error_code_on_missing_session(self):
        """SessionNotFoundError must produce error_code='not_found'."""
        from openroad_mcp.interactive.models import SessionNotFoundError

        manager = _make_manager()
        manager.inspect_session = AsyncMock(side_effect=SessionNotFoundError("s99"))
        tool = InspectSessionTool(manager)
        raw = asyncio.run(tool.execute("s99"))
        data = json.loads(raw)
        assert data.get("error_code") == "not_found", f"Expected error_code='not_found', got {data.get('error_code')!r}"

    def test_terminate_sets_terminated_true(self):
        """Successful termination must return terminated=True."""
        manager = _make_manager()
        session_info = MagicMock()
        session_info.is_alive = True
        manager.get_session_info = AsyncMock(return_value=session_info)
        manager.terminate_session = AsyncMock(return_value=None)
        tool = TerminateSessionTool(manager)
        raw = asyncio.run(tool.execute("s1", force=False))
        data = json.loads(raw)
        assert data["terminated"] is True, "terminated must be True on success"

    def test_history_total_commands_matches_array(self):
        """total_commands must equal len(history) in the response."""
        manager = _make_manager()
        manager.get_session_history = AsyncMock(
            return_value=[
                {"command": "puts hello", "timestamp": "2026-01-01T00:00:00", "id": 1},
                {"command": "puts world", "timestamp": "2026-01-01T00:00:01", "id": 2},
            ]
        )
        tool = SessionHistoryTool(manager)
        raw = asyncio.run(tool.execute("s1"))
        data = json.loads(raw)
        assert data["total_commands"] == len(data["history"]), "total_commands must equal len(history)"

    def test_error_code_is_valid_enum_value_or_null(self):
        """error_code in any result must be a valid ErrorCode value or null."""
        valid = {e.value for e in ErrorCode} | {None}
        manager = _make_manager()
        manager.list_sessions = AsyncMock(return_value=[])
        tool = ListSessionsTool(manager)
        raw = asyncio.run(tool.execute())
        data = json.loads(raw)
        assert data.get("error_code") in valid, f"error_code {data.get('error_code')!r} is not a valid ErrorCode"


# ---------------------------------------------------------------------------
# 3. Tool description quality
# ---------------------------------------------------------------------------


class TestToolDescriptionQuality:
    """Score each tool's docstring against a rubric; every tool must score ≥6/10."""

    TOOLS = [
        "interactive_openroad",
        "list_interactive_sessions",
        "create_interactive_session",
        "terminate_interactive_session",
        "inspect_interactive_session",
        "get_session_history",
        "get_session_metrics",
        "list_report_images",
        "read_report_image",
    ]

    @staticmethod
    def _score_docstring(name: str, doc: str) -> tuple[int, list[str]]:
        """Return (score, reasons) for a docstring."""
        score = 0
        reasons = []
        words = doc.split()

        if len(words) >= 20:
            score += 2
        else:
            reasons.append(f"too short ({len(words)} words, need ≥20)")

        if any(w in doc.lower() for w in ("returns", "return")):
            score += 2
        else:
            reasons.append("missing 'returns'/'return' keyword")

        if any(c in doc for c in ("(", "str", "int", "bool", "dict", "list", "null")):
            score += 2
        else:
            reasons.append("no field type mentions")

        if "error" in doc.lower():
            score += 2
        else:
            reasons.append("no mention of 'error'")

        params = [ln.strip() for ln in doc.splitlines() if ":" in ln and ln.strip() and not ln.strip().startswith("-")]
        short_params = [p for p in params if len(p.split(":")[0].strip()) == 1]
        if not short_params:
            score += 2
        else:
            reasons.append(f"single-letter param hint found: {short_params}")

        return score, reasons

    def _get_tool_doc(self, tool_name: str) -> str:
        from openroad_mcp import server as srv

        fn = getattr(srv, tool_name, None)
        assert fn is not None, f"Tool function '{tool_name}' not found in server module"
        # FastMCP wraps functions in FunctionTool; access description or underlying fn.__doc__
        if hasattr(fn, "description") and fn.description:
            return fn.description.strip()
        if hasattr(fn, "fn") and fn.fn.__doc__:
            return fn.fn.__doc__.strip()
        return (fn.__doc__ or "").strip()

    @pytest.mark.parametrize("tool_name", TOOLS)
    def test_tool_description_quality(self, tool_name: str):
        doc = self._get_tool_doc(tool_name)
        score, reasons = self._score_docstring(tool_name, doc)
        assert score >= 6, f"{tool_name} scored {score}/10. Issues: {'; '.join(reasons)}\nDocstring:\n{doc[:300]}"


# ---------------------------------------------------------------------------
# 4. Latency percentiles (serialization only, no PTY I/O)
# ---------------------------------------------------------------------------


class TestLatencyPercentiles:
    """Measure p50/p90/p99 for pure JSON serialization; no PTY or network I/O."""

    ITERATIONS = 200

    def _collect_latencies(self) -> list[float]:
        result = InteractiveExecResult(
            output="set x [expr 1 + 1]",
            session_id="bench-session",
            timestamp="2026-01-01T12:00:00",
            execution_time=0.042,
            command_count=10,
            buffer_size=2048,
        )
        latencies = []
        data = result.model_dump()
        for _ in range(self.ITERATIONS):
            t0 = time.perf_counter()
            json.dumps(data, separators=(",", ":"))
            latencies.append(time.perf_counter() - t0)
        return latencies

    @staticmethod
    def _percentile(data: list[float], pct: float) -> float:
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]

    def test_p99_under_1ms(self):
        """p99 serialization latency must be under 1 ms."""
        latencies = self._collect_latencies()
        p99 = self._percentile(latencies, 99)
        assert p99 < 0.001, f"p99={p99 * 1000:.3f}ms exceeds 1ms budget"

    def test_p90_under_0_5ms(self):
        """p90 serialization latency must be under 0.5 ms."""
        latencies = self._collect_latencies()
        p90 = self._percentile(latencies, 90)
        assert p90 < 0.0005, f"p90={p90 * 1000:.3f}ms exceeds 0.5ms budget"

    def test_p50_under_0_1ms(self):
        """p50 (median) serialization latency must be under 0.1 ms."""
        latencies = self._collect_latencies()
        p50 = self._percentile(latencies, 50)
        assert p50 < 0.0001, f"p50={p50 * 1000:.3f}ms exceeds 0.1ms budget"

    def test_latency_report(self, capsys):
        """Print a human-readable latency report (always passes)."""
        latencies = self._collect_latencies()
        p50 = self._percentile(latencies, 50)
        p90 = self._percentile(latencies, 90)
        p99 = self._percentile(latencies, 99)
        print(
            f"\nJSON serialization latency ({self.ITERATIONS} iterations):\n"
            f"  p50={p50 * 1000:.4f}ms  p90={p90 * 1000:.4f}ms  p99={p99 * 1000:.4f}ms"
        )
