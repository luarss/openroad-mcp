"""Code Mode - Compact tool interface for OpenROAD.

Code Mode provides two tools that give full access to OpenROAD's Tcl commands
while minimizing context window usage:

- code_search: Discover available OpenROAD commands by name, category, or keyword
- code_execute: Execute Tcl code in an OpenROAD session

This pattern reduces token footprint from potentially tens of thousands
(tools for each command) to ~1,000 tokens while maintaining full access.
"""

from .executor import CodeModeExecutor
from .models import CodeExecuteResult, CodeSearchResult, CommandInfo
from .registry import CommandRegistry, registry
from .sandbox import CodeSandbox

__all__ = [
    "CodeModeExecutor",
    "CodeSearchResult",
    "CodeExecuteResult",
    "CommandInfo",
    "CommandRegistry",
    "CodeSandbox",
    "registry",
]
