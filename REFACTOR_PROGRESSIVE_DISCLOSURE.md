# Refactor: Progressive Disclosure for MCP Tools

## Problem

Every MCP tool definition (name + description + parameter schema) is injected into the model's context on every request. With 10 tools — many diagnostic and rarely needed — the model burns context budget and faces unnecessary decision overhead on every call.

Progressive disclosure at the MCP layer means: surface only what's needed for the common case, keep advanced functionality accessible but not foregrounded.

---

## Changes

### 1. Consolidate 3 diagnostic session tools → `get_session_info`

**Remove** these 3 MCP-registered tools (keep underlying classes as internal helpers):
- `inspect_interactive_session`
- `get_session_history`
- `get_session_metrics`

**Add** a single `get_session_info` tool:

```python
async def get_session_info(
    session_id: str | None = None,
    mode: Literal["inspect", "history", "metrics"] = "inspect",
    limit: int | None = None,   # history mode only
    search: str | None = None,  # history mode only
) -> str:
    """Get diagnostic information for an interactive OpenROAD session.

    mode options:
      "inspect"  — session state, uptime, memory, buffer utilization (default)
      "history"  — command history; use limit and search to filter
      "metrics"  — performance metrics across all sessions (session_id unused)

    Call list_interactive_sessions first to discover session IDs.
    """
```

Dispatch logic:
- `"inspect"` → `inspect_session_tool.execute(session_id)`
- `"history"` → `session_history_tool.execute(session_id, limit, search)`
- `"metrics"` → `session_metrics_tool.execute()` (session_id ignored)

**Result: 10 tools → 7 tools**

---

### 2. Enrich all tool descriptions with workflow guidance

Update docstrings in `server.py`. Current descriptions are 1–2 lines with no workflow context. New descriptions tell the model: when to use this, what to do after, and what to use instead.

**`create_interactive_session`:**
```
Create a new interactive OpenROAD session.

You can skip this — interactive_openroad_exec and interactive_openroad_query
auto-create a session if none is provided. Call this explicitly only when you
need to control the session ID, working directory, or environment.

After creation, use interactive_openroad_exec to load your design:
  read_lef <path>, read_liberty <path>, read_verilog <path>, link_design <name>
```

**`interactive_openroad_exec`:**
```
Execute a state-modifying OpenROAD command (set_*, create_*, read_*, write_*, flow commands).

Use this for loading designs, running placement/routing, applying constraints,
and writing outputs. If no session_id is given, a session is auto-created and
its ID is returned — save it for subsequent calls.

Typical sequence: read_lef → read_liberty → read_verilog → link_design → run flow steps.
Read-only commands are blocked — use interactive_openroad_query instead.
```

**`interactive_openroad_query`:**
```
Execute a read-only OpenROAD command (report_*, get_*, check_*, sta, help, etc.).

Use this for querying design state, generating reports, and inspecting timing.
If no session_id is given, a session is auto-created and its ID is returned.
Commands that modify design state are blocked — use interactive_openroad_exec instead.
```

**`list_interactive_sessions`:**
```
List all active interactive OpenROAD sessions with their IDs and status.

Call this first when you don't know which sessions exist. Use the returned
session_ids with interactive_openroad_exec, interactive_openroad_query, or
get_session_info.
```

**`terminate_interactive_session`:**
```
Terminate an interactive OpenROAD session. Set force=true only if the session
is unresponsive. After termination the session_id is no longer valid.
```

**`list_report_images` / `read_report_image`:** add a note that these require ORFS to be installed and a run to have completed.

---

### 3. Add `next_steps` hint to `create_interactive_session` response

When a session is created successfully, include a `next_steps` field so the model immediately knows what to do next without re-reading descriptions.

**Response shape change** (`InteractiveSessionInfo` in `core/models.py`):
```json
{
  "session_id": "session-abc123",
  "is_alive": true,
  "created_at": "...",
  "next_steps": "Session ready. Load your design with interactive_openroad_exec: read_lef, read_liberty, read_verilog, then link_design."
}
```

Add `next_steps: str | None = None` to `InteractiveSessionInfo`. Set it in `CreateSessionTool.execute()` after successful creation.

---

## Files to Modify

| File | Change |
|------|--------|
| `src/openroad_mcp/server.py` | Remove 3 tool registrations + instances, add `get_session_info`, update all 7 descriptions |
| `src/openroad_mcp/tools/interactive.py` | Add `GetSessionInfoTool`; update `CreateSessionTool` to populate `next_steps` |
| `src/openroad_mcp/core/models.py` | Add `next_steps: str | None = None` to `InteractiveSessionInfo` |
| `tests/tools/test_interactive_tools.py` | Add `GetSessionInfoTool` tests (3 modes); remove tests for the 3 merged tools |

---

## Verification

```bash
# Unit tests
uv run pytest tests/tools/test_interactive_tools.py -v

# Full suite — no regressions
uv run pytest

# Manual: connect MCP client and verify 7 tools listed (not 10)
# Manual: create session → exec read_lef → query report_checks → get_session_info (each mode)
```
