"""OpenROAD command registry for Code Mode search functionality."""

import fnmatch
from typing import ClassVar

from .models import CommandInfo


class CommandRegistry:
    """Registry of OpenROAD commands organized by category."""

    # Command categories with their commands and descriptions
    CATEGORIES: ClassVar[dict[str, list[dict[str, str | list[str] | None]]]] = {
        "reporting": [
            {"name": "report_timing", "description": "Report timing paths and slack"},
            {"name": "report_design_area", "description": "Report total design area"},
            {"name": "report_cell_usage", "description": "Report cell usage statistics"},
            {"name": "report_power", "description": "Report power analysis results"},
            {"name": "report_clock_properties", "description": "Report clock properties"},
            {"name": "report_cts", "description": "Report clock tree synthesis status"},
            {"name": "report_floating_nets", "description": "Report floating nets in design"},
            {"name": "report_checks", "description": "Report design rule checks"},
            {"name": "report_parasitic_annotation", "description": "Report parasitic annotation status"},
            {"name": "report_units", "description": "Report current unit settings"},
        ],
        "query": [
            {"name": "get_cells", "description": "Get cell instances in design"},
            {"name": "get_nets", "description": "Get nets in design"},
            {"name": "get_ports", "description": "Get ports in design"},
            {"name": "get_pins", "description": "Get pins in design"},
            {"name": "get_clocks", "description": "Get clocks in design"},
            {"name": "get_lib_cells", "description": "Get library cells"},
            {"name": "get_lib_pins", "description": "Get library pins"},
            {"name": "get_timing_paths", "description": "Get timing paths"},
        ],
        "constraints": [
            {"name": "set_input_delay", "description": "Set input delay constraint"},
            {"name": "set_output_delay", "description": "Set output delay constraint"},
            {"name": "set_load", "description": "Set load on port or net"},
            {"name": "set_driving_cell", "description": "Set driving cell for port"},
            {"name": "set_wire_rc", "description": "Set wire resistance/capacitance"},
            {"name": "set_clock_latency", "description": "Set clock latency"},
            {"name": "set_clock_uncertainty", "description": "Set clock uncertainty (jitter/skew)"},
            {"name": "set_propagated_clock", "description": "Mark clock as propagated"},
            {"name": "set_timing_derate", "description": "Set timing derating factors"},
            {"name": "set_max_fanout", "description": "Set maximum fanout constraint"},
            {"name": "set_max_capacitance", "description": "Set maximum capacitance"},
            {"name": "set_max_transition", "description": "Set maximum transition time"},
            {"name": "create_clock", "description": "Create a clock object"},
            {"name": "create_generated_clock", "description": "Create a generated clock"},
            {"name": "create_virtual_clock", "description": "Create a virtual clock for constraints"},
        ],
        "io": [
            {"name": "read_lef", "description": "Read LEF library file"},
            {"name": "read_def", "description": "Read DEF design file"},
            {"name": "read_verilog", "description": "Read Verilog netlist"},
            {"name": "read_liberty", "description": "Read Liberty timing library"},
            {"name": "read_sdc", "description": "Read SDC constraints file"},
            {"name": "read_spef", "description": "Read SPEF parasitics file"},
            {"name": "write_lef", "description": "Write LEF output"},
            {"name": "write_def", "description": "Write DEF output"},
            {"name": "write_verilog", "description": "Write Verilog netlist"},
            {"name": "write_sdf", "description": "Write SDF delay file"},
            {"name": "write_spef", "description": "Write SPEF parasitics"},
        ],
        "floorplan": [
            {"name": "initialize_floorplan", "description": "Initialize floorplan with die/core area"},
            {"name": "place_pins", "description": "Place pins on block boundary"},
            {"name": "make_io_sites", "description": "Create I/O site definitions"},
            {"name": "place_pad", "description": "Place I/O pad instances"},
            {"name": "remove_buffers", "description": "Remove buffers from design"},
            {"name": "add_global_connect", "description": "Add global net connections"},
        ],
        "placement": [
            {"name": "global_placement", "description": "Run global placement"},
            {"name": "detailed_placement", "description": "Run detailed placement (legalization)"},
            {"name": "place_cell", "description": "Place a specific cell instance"},
            {"name": "remove_placement", "description": "Remove placement information"},
            {"name": "density_fill", "description": "Add fill cells for density"},
            {"name": "optimize_mirroring", "description": "Optimize cell orientation"},
        ],
        "routing": [
            {"name": "global_route", "description": "Run global routing"},
            {"name": "detailed_route", "description": "Run detailed routing"},
            {"name": "repair_antennas", "description": "Fix antenna violations"},
            {"name": "filler_placement", "description": "Place filler cells"},
            {"name": "check_routing_nets", "description": "Check routing completion"},
        ],
        "cts": [
            {"name": "clock_tree_synthesis", "description": "Run clock tree synthesis"},
            {"name": "repair_clock_nets", "description": "Repair clock net violations"},
            {"name": "balance_clocks", "description": "Balance clock tree"},
        ],
        "timing": [
            {"name": "sta", "description": "Run static timing analysis"},
            {"name": "repair_timing", "description": "Repair timing violations with buffering"},
            {"name": "estimate_parasitics", "description": "Estimate parasitic capacitance/resistance"},
            {"name": "find_clocks", "description": "Auto-detect clocks in design"},
            {"name": "set_propagated_clock", "description": "Enable propagated clock analysis"},
        ],
        "verification": [
            {"name": "check_placement", "description": "Verify placement legality"},
            {"name": "check_route", "description": "Verify routing completion"},
            {"name": "check_antennas", "description": "Check for antenna violations"},
            {"name": "check_lvs", "description": "Run layout vs schematic check"},
            {"name": "check_design", "description": "Check design consistency"},
            {"name": "verify_connectivity", "description": "Verify all nets are connected"},
            {"name": "verify_geometry", "description": "Verify geometric design rules"},
            {"name": "verify_drc", "description": "Run design rule check"},
        ],
        "utility": [
            {"name": "help", "description": "Show command help"},
            {"name": "version", "description": "Show OpenROAD version"},
            {"name": "log_begin", "description": "Begin command logging to file"},
            {"name": "log_end", "description": "End command logging"},
        ],
        "tcl_builtins": [
            {"name": "puts", "description": "Print output to stdout", "is_safe": True},
            {"name": "set", "description": "Set variable value", "is_safe": True},
            {"name": "expr", "description": "Evaluate expression", "is_safe": True},
            {"name": "if", "description": "Conditional execution", "is_safe": True},
            {"name": "else", "description": "Else clause", "is_safe": True},
            {"name": "elseif", "description": "Else-if clause", "is_safe": True},
            {"name": "for", "description": "For loop", "is_safe": True},
            {"name": "foreach", "description": "Iterate over list", "is_safe": True},
            {"name": "while", "description": "While loop", "is_safe": True},
            {"name": "proc", "description": "Define procedure", "is_safe": True},
            {"name": "return", "description": "Return from procedure", "is_safe": True},
            {"name": "break", "description": "Break from loop", "is_safe": True},
            {"name": "continue", "description": "Continue loop iteration", "is_safe": True},
            {"name": "list", "description": "Create list", "is_safe": True},
            {"name": "llength", "description": "Get list length", "is_safe": True},
            {"name": "lindex", "description": "Get list element", "is_safe": True},
            {"name": "lappend", "description": "Append to list", "is_safe": True},
            {"name": "lrange", "description": "Get list range", "is_safe": True},
            {"name": "lsort", "description": "Sort list", "is_safe": True},
            {"name": "lsearch", "description": "Search list", "is_safe": True},
            {"name": "string", "description": "String operations", "is_safe": True},
            {"name": "regexp", "description": "Regular expression match", "is_safe": True},
            {"name": "regsub", "description": "Regular expression substitution", "is_safe": True},
            {"name": "format", "description": "Format string", "is_safe": True},
            {"name": "array", "description": "Array operations", "is_safe": True},
            {"name": "dict", "description": "Dictionary operations", "is_safe": True},
            {"name": "catch", "description": "Catch errors", "is_safe": True},
            {"name": "info", "description": "Get interpreter info", "is_safe": True},
            {"name": "incr", "description": "Increment variable", "is_safe": True},
            {"name": "append", "description": "Append to string", "is_safe": True},
        ],
    }

    def search(self, query: str, max_results: int = 50) -> list[CommandInfo]:
        """Search commands by name, category, or description.

        Args:
            query: Search query (command name, category, or keyword)
            max_results: Maximum number of results to return

        Returns:
            List of matching CommandInfo objects
        """
        query_lower = query.lower().strip()
        results: list[CommandInfo] = []

        # Return empty for empty queries
        if not query_lower:
            return []

        # Check if query is a specific category
        if query_lower in self.CATEGORIES:
            for cmd in self.CATEGORIES[query_lower]:
                results.append(
                    CommandInfo(
                        name=cmd["name"],
                        category=query_lower,
                        description=cmd.get("description"),
                        arguments=cmd.get("arguments"),  # type: ignore
                        is_safe=cmd.get("is_safe", True),
                    )
                )
            return results[:max_results]

        # Search across all categories
        for category, commands in self.CATEGORIES.items():
            for cmd in commands:
                name = cmd["name"].lower()
                desc = (cmd.get("description") or "").lower()

                # Match by name (exact or pattern), description, or category
                if (
                    query_lower == name
                    or query_lower in name
                    or fnmatch.fnmatch(name, f"*{query_lower}*")
                    or query_lower in desc
                    or query_lower in category
                ):
                    results.append(
                        CommandInfo(
                            name=cmd["name"],
                            category=category,
                            description=cmd.get("description"),
                            arguments=cmd.get("arguments"),  # type: ignore
                            is_safe=cmd.get("is_safe", True),
                        )
                    )

        return results[:max_results]

    def get_categories(self) -> list[str]:
        """Get all available command categories.

        Returns:
            List of category names
        """
        return list(self.CATEGORIES.keys())

    def get_by_category(self, category: str) -> list[CommandInfo]:
        """Get all commands in a specific category.

        Args:
            category: Category name

        Returns:
            List of CommandInfo objects in the category
        """
        if category not in self.CATEGORIES:
            return []

        return [
            CommandInfo(
                name=cmd["name"],
                category=category,
                description=cmd.get("description"),
                arguments=cmd.get("arguments"),  # type: ignore
                is_safe=cmd.get("is_safe", True),
            )
            for cmd in self.CATEGORIES[category]
        ]

    def get_command(self, name: str) -> CommandInfo | None:
        """Get a specific command by name.

        Args:
            name: Command name

        Returns:
            CommandInfo if found, None otherwise
        """
        for category, commands in self.CATEGORIES.items():
            for cmd in commands:
                if cmd["name"] == name:
                    return CommandInfo(
                        name=cmd["name"],
                        category=category,
                        description=cmd.get("description"),
                        arguments=cmd.get("arguments"),  # type: ignore
                        is_safe=cmd.get("is_safe", True),
                    )
        return None


# Global registry instance
registry = CommandRegistry()
