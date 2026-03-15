"""Command whitelist for OpenROAD PTY session security.

Defines allowed Tcl/OpenROAD command patterns for interactive PTY sessions.
Prevents accidental execution of destructive system-level commands by AI agents.

Design: deny-by-default. A command verb must match at least one pattern in the
relevant pattern set and must NOT appear in BLOCKED_COMMANDS to be permitted.
"""

import fnmatch

from ..utils.logging import get_logger

logger = get_logger("command_whitelist")

# Explicitly blocked commands — take priority over all pattern sets.
BLOCKED_COMMANDS: frozenset[str] = frozenset(
    [
        "exec",  # OS-level command execution
        "source",  # Load and run arbitrary Tcl scripts
        "exit",  # Terminate the OpenROAD process
        "quit",  # Terminate the OpenROAD process
        "open",  # Raw file-handle I/O
        "close",  # File-handle close
        "socket",  # Network connections
        "load",  # Load compiled C extensions into the interpreter
        "file",  # Filesystem manipulation (delete, rename, mkdir…)
        "cd",  # Change working directory
        "glob",  # Filesystem enumeration
        "fconfigure",  # I/O channel configuration
        "chan",  # Channel operations
        "vwait",  # Block the event loop
        "rename",  # Renames/removes commands, can bypass top-level checks
        "uplevel",  # Evaluates script in a different stack level
        "after",  # Schedules arbitrary code execution
        "subst",  # Performs substitutions that can invoke arbitrary commands
    ]
)

# Safe Tcl built-ins — included in both pattern sets.
_TCL_BUILTINS: tuple[str, ...] = (
    "puts",
    "set",
    "expr",
    "if",
    "else",
    "elseif",
    "for",
    "foreach",
    "while",
    "proc",
    "return",
    "break",
    "continue",
    "list",
    "llength",
    "lindex",
    "lappend",
    "lrange",
    "lsort",
    "lsearch",
    "lreplace",
    "string",
    "regexp",
    "regsub",
    "format",
    "scan",
    "array",
    "dict",
    "catch",
    "error",
    "namespace",
    "upvar",
    "global",
    "variable",
    "concat",
    "join",
    "split",
    "incr",
    "append",
    "info",
    "unset",
)

# Read-only OpenROAD commands: reporting, querying, checking, and analysis.
# Use with interactive_openroad_query.
READONLY_PATTERNS: tuple[str, ...] = (
    # ── OpenROAD reporting ────────────────────────────────────────────────
    "report_*",
    # ── OpenROAD design queries ───────────────────────────────────────────
    "get_*",
    # ── OpenROAD validation ───────────────────────────────────────────────
    "check_*",
    # ── OpenROAD analysis ─────────────────────────────────────────────────
    "estimate_parasitics",
    "sta",
    # ── OpenROAD utility ──────────────────────────────────────────────────
    "help",
    "version",
) + _TCL_BUILTINS

# State-modifying OpenROAD commands: flow execution, file I/O, design changes.
# Use with interactive_openroad_exec.
MODIFY_PATTERNS: tuple[str, ...] = (
    # ── OpenROAD constraints / design setup ──────────────────────────────
    "set_*",
    "create_*",
    # ── File I/O through OpenROAD wrappers ───────────────────────────────
    "read_*",
    "write_*",
    # ── OpenROAD flow commands ────────────────────────────────────────────
    "initialize_floorplan",
    "place_pins",
    "global_placement",
    "detailed_placement",
    "clock_tree_synthesis",
    "global_route",
    "detailed_route",
    "repair_design",
    "repair_timing",
    "repair_clock_nets",
    # ── OpenROAD utility ──────────────────────────────────────────────────
    "log_begin",
    "log_end",
) + _TCL_BUILTINS

# Union of both sets — used by is_command_allowed for backward compatibility.
ALLOWED_PATTERNS: tuple[str, ...] = tuple(dict.fromkeys(READONLY_PATTERNS + MODIFY_PATTERNS))


def _extract_verb(statement: str) -> str | None:
    """Return the command verb (first token) of a single Tcl statement.

    Returns None for blank lines, comments, and lines that start with a
    substitution or grouping character (not a bare command invocation).
    """
    stripped = statement.strip()
    if not stripped or stripped.startswith("#"):
        return None
    # Lines beginning with $ or [ are sub-expressions, not top-level commands.
    if stripped[0] in ("$", "[", "]", "{", "}"):
        return None
    return stripped.split()[0].rstrip(";")


def _check_command(command: str, patterns: tuple[str, ...]) -> tuple[bool, str | None]:
    """Validate every statement in *command* against *patterns* and BLOCKED_COMMANDS.

    Multi-statement inputs (separated by ``;`` or newlines) are checked
    individually — all must be allowed.

    **Known limitation**: semicolons are split naively with
    ``command.replace(";", "\\n")``.  Semicolons inside Tcl braces or quoted
    strings (e.g. ``puts {hello; world}``) will cause the text after the
    semicolon to be evaluated as a separate statement and may be rejected even
    though the original command is safe.
    # TODO: replace the naive splitter with a Tcl-aware one that ignores
    # semicolons inside ``{...}`` and quoted strings.

    Returns:
        ``(True, None)`` if every statement is permitted.
        ``(False, verb)`` where *verb* is the first blocked command name.
    """
    for raw_line in command.replace(";", "\n").splitlines():
        verb = _extract_verb(raw_line)
        if verb is None:
            continue

        # Explicit block list takes priority over patterns.
        if verb in BLOCKED_COMMANDS:
            logger.warning("Blocked command '%s' (explicit blocklist)", verb)
            return False, verb

        # Must match at least one allowed pattern.
        if not any(fnmatch.fnmatch(verb, pattern) for pattern in patterns):
            logger.warning("Blocked command '%s' (not in whitelist)", verb)
            return False, verb

    return True, None


def is_command_allowed(command: str) -> tuple[bool, str | None]:
    """Check *command* against the full union of READONLY and MODIFY patterns."""
    return _check_command(command, ALLOWED_PATTERNS)


def is_readonly_command(command: str) -> tuple[bool, str | None]:
    """Check *command* against READONLY_PATTERNS only."""
    return _check_command(command, READONLY_PATTERNS)


def is_modify_command(command: str) -> tuple[bool, str | None]:
    """Check *command* against MODIFY_PATTERNS only."""
    return _check_command(command, MODIFY_PATTERNS)
