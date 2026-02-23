"""Command whitelist for OpenROAD PTY session security.

Defines allowed Tcl/OpenROAD command patterns for interactive PTY sessions.
Prevents accidental execution of destructive system-level commands by AI agents.

Design: deny-by-default. A command verb must match at least one pattern in
ALLOWED_PATTERNS and must NOT appear in BLOCKED_COMMANDS to be permitted.
"""

import fnmatch

from ..utils.logging import get_logger

logger = get_logger("command_whitelist")

# Explicitly blocked commands — take priority over ALLOWED_PATTERNS.
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
    ]
)

# Glob patterns (fnmatch) for permitted command verbs.
ALLOWED_PATTERNS: tuple[str, ...] = (
    # ── OpenROAD reporting ────────────────────────────────────────────────
    "report_*",
    # ── OpenROAD design queries ───────────────────────────────────────────
    "get_*",
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
    "check_placement",
    "check_route",
    "check_antennas",
    "estimate_parasitics",
    "sta",
    # ── OpenROAD utility ──────────────────────────────────────────────────
    "help",
    "version",
    "log_begin",
    "log_end",
    # ── Safe Tcl built-ins ────────────────────────────────────────────────
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
    "uplevel",
    "subst",
    "unset",
    "rename",
    "after",
)


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


def is_command_allowed(command: str) -> tuple[bool, str | None]:
    """Validate that every statement in *command* is on the allowlist.

    Multi-statement inputs (separated by ``;`` or newlines) are checked
    individually — all must be allowed.

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
        if not any(fnmatch.fnmatch(verb, pattern) for pattern in ALLOWED_PATTERNS):
            logger.warning("Blocked command '%s' (not in whitelist)", verb)
            return False, verb

    return True, None
