"""Basic timing command parsers for OpenSTA output"""

import re
from typing import Any

from .models import PathInfo


class BasicTimingParser:
    """Simple parser for core timing command outputs"""

    WNS_PATTERN = re.compile(r"wns\s+(?:max|min)?\s*([-\d.]+)", re.IGNORECASE)
    TNS_PATTERN = re.compile(r"tns\s+(?:max|min)?\s*([-\d.]+)", re.IGNORECASE)

    PATH_START_PATTERN = re.compile(r"Startpoint:\s+(\S+)", re.MULTILINE)
    PATH_END_PATTERN = re.compile(r"Endpoint:\s+(\S+)", re.MULTILINE)
    PATH_GROUP_PATTERN = re.compile(r"Path Group:\s+(\S+)", re.MULTILINE)
    PATH_TYPE_PATTERN = re.compile(r"Path Type:\s+(\S+)", re.MULTILINE)

    SLACK_PATTERN = re.compile(r"([-\d.]+)\s+slack\s+\(.*?\)", re.IGNORECASE)
    ARRIVAL_PATTERN = re.compile(r"([-\d.]+)\s+data arrival time", re.IGNORECASE)
    REQUIRED_PATTERN = re.compile(r"([-\d.]+)\s+data required time", re.IGNORECASE)

    ERROR_PATTERNS = [
        re.compile(r"\[ERROR\]", re.IGNORECASE),
        re.compile(r"Error:", re.IGNORECASE),
        re.compile(r"command not found", re.IGNORECASE),
        re.compile(r"No such file", re.IGNORECASE),
    ]

    @staticmethod
    def parse_wns_tns(output: str, command: str) -> dict[str, Any]:
        """Extract WNS or TNS value from report output

        Args:
            output: Command output text
            command: Command that was executed (for context)

        Returns:
            Dictionary with 'value' key containing the parsed number
        """
        is_wns = "wns" in command.lower()
        pattern = BasicTimingParser.WNS_PATTERN if is_wns else BasicTimingParser.TNS_PATTERN

        match = pattern.search(output)
        if match:
            value = float(match.group(1))
            return {"value": value, "type": "wns" if is_wns else "tns"}

        return {"value": None, "type": "wns" if is_wns else "tns", "error": "Could not parse value"}

    @staticmethod
    def parse_report_checks(output: str) -> list[PathInfo]:
        """Extract basic path information from report_checks

        Args:
            output: report_checks command output

        Returns:
            List of PathInfo objects for each path found
        """
        paths = []

        path_blocks = output.split("Startpoint:")

        for block in path_blocks[1:]:
            block = "Startpoint:" + block
            path = BasicTimingParser._parse_single_path(block)
            if path:
                paths.append(path)

        return paths

    @staticmethod
    def _parse_single_path(block: str) -> PathInfo | None:
        """Parse a single timing path block"""
        start_match = BasicTimingParser.PATH_START_PATTERN.search(block)
        end_match = BasicTimingParser.PATH_END_PATTERN.search(block)
        group_match = BasicTimingParser.PATH_GROUP_PATTERN.search(block)
        slack_match = BasicTimingParser.SLACK_PATTERN.search(block)

        if not (start_match and end_match and slack_match):
            return None

        type_match = BasicTimingParser.PATH_TYPE_PATTERN.search(block)
        arrival_match = BasicTimingParser.ARRIVAL_PATTERN.search(block)
        required_match = BasicTimingParser.REQUIRED_PATTERN.search(block)

        return PathInfo(
            startpoint=start_match.group(1),
            endpoint=end_match.group(1),
            path_group=group_match.group(1) if group_match else "unknown",
            slack=float(slack_match.group(1)),
            path_type=type_match.group(1) if type_match else None,
            arrival=float(arrival_match.group(1)) if arrival_match else None,
            required=float(required_match.group(1)) if required_match else None,
        )

    @staticmethod
    def parse_fanin_fanout(output: str) -> list[str]:
        """Extract pin list from fanin/fanout commands

        Args:
            output: get_fanin or get_fanout command output

        Returns:
            List of pin paths
        """
        pins = []

        for line in output.strip().split("\n"):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if parts:
                pins.append(parts[0])

        return pins

    @staticmethod
    def detect_error(output: str) -> str | None:
        """Detect OpenROAD errors in command output

        Args:
            output: Command output to check

        Returns:
            Error message if found, None otherwise
        """
        for pattern in BasicTimingParser.ERROR_PATTERNS:
            if pattern.search(output):
                lines = output.split("\n")
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        context = "\n".join(lines[start:end])
                        return context

        return None
