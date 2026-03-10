#!/usr/bin/env python3
"""
MCP Integration Test Runner

Runs test cases against the MCP server using the MCP Inspector CLI.
Tests are defined in test_cases.json.

Benefits of MCP Inspector CLI:
- No API key or OAuth required
- Direct MCP protocol access (deterministic JSON output)
- Faster execution (no LLM inference)
- Free (no API costs)

Usage:
    python run_tests.py                          # Run discovery tests only
    python run_tests.py --all                    # Run all tests including session tests
    python run_tests.py --category session       # Run specific category
    python run_tests.py --list                   # List available tests

Environment:
    OPENROAD_EXE   - Path to openroad binary (required for session tests)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    category: str
    passed: bool
    duration_seconds: float
    output: str
    error: str | None = None
    expected_found: list[str] | None = None
    expected_missing: list[str] | None = None


class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color

    @classmethod
    def disable(cls) -> None:
        """Disable colors for non-TTY output."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.NC = ""


class MCPTestRunner:
    """Runs MCP integration tests using MCP Inspector CLI."""

    def __init__(
        self,
        mcp_config: Path,
        test_cases_file: Path,
        results_dir: Path | None = None,
    ):
        self.mcp_config = mcp_config
        self.results_dir = results_dir or Path(".test-results/mcp-cli")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        with open(test_cases_file) as f:
            self.test_cases = json.load(f)

    def check_prerequisites(self, require_openroad: bool = False) -> bool:
        """Verify all prerequisites are met."""
        print(f"{Colors.YELLOW}Checking prerequisites...{Colors.NC}")

        # Check Node.js
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                print(f"  {Colors.GREEN}✓{Colors.NC} Node.js found: {result.stdout.strip()}")
            else:
                print(f"  {Colors.RED}✗{Colors.NC} Node.js returned error")
                return False
        except FileNotFoundError:
            print(f"  {Colors.RED}✗{Colors.NC} Node.js not found")
            return False
        except subprocess.TimeoutExpired:
            print(f"  {Colors.RED}✗{Colors.NC} Node.js timed out")
            return False

        # Check MCP config
        if not self.mcp_config.exists():
            print(f"  {Colors.RED}✗{Colors.NC} MCP config not found: {self.mcp_config}")
            return False
        print(f"  {Colors.GREEN}✓{Colors.NC} MCP config found: {self.mcp_config}")

        # Check OpenROAD if required
        if require_openroad:
            openroad_exe = os.environ.get("OPENROAD_EXE")
            if not openroad_exe or not Path(openroad_exe).exists():
                print(f"  {Colors.RED}✗{Colors.NC} OPENROAD_EXE not set or not found")
                return False
            print(f"  {Colors.GREEN}✓{Colors.NC} OpenROAD found: {openroad_exe}")

        print()
        return True

    def run_mcp_method(
        self,
        method: str,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> tuple[str, str, int]:
        """
        Run an MCP method through MCP Inspector CLI.

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        cmd = [
            "npx",
            "@modelcontextprotocol/inspector@latest",
            "--cli",
            "--config",
            str(self.mcp_config),
            "--server",
            "openroad-mcp",
            "--method",
            method,
        ]

        if tool_name:
            cmd.extend(["--tool-name", tool_name])

        if tool_args:
            for key, value in tool_args.items():
                # Convert value to JSON string for complex types
                if isinstance(value, dict | list):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)
                cmd.extend(["--tool-arg", f"{key}={value_str}"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", 124

    def check_output(
        self,
        output: str,
        expect_contains: list[str] | None,
        expect_not_contains: list[str] | None = None,
    ) -> tuple[bool, list[str], list[str]]:
        """
        Check if output contains expected patterns.

        Returns:
            Tuple of (passed, found_patterns, missing_patterns)
        """
        output_lower = output.lower()
        found: list[str] = []
        missing: list[str] = []

        if expect_contains:
            for pattern in expect_contains:
                if re.search(pattern.lower(), output_lower):
                    found.append(pattern)
                else:
                    missing.append(pattern)

        if expect_not_contains:
            for pattern in expect_not_contains:
                if re.search(pattern.lower(), output_lower):
                    missing.append(f"should not contain: {pattern}")

        passed = len(missing) == 0
        return passed, found, missing

    def run_test(
        self,
        test: dict[str, Any],
        category: str,
        session_id: str | None = None,
    ) -> TestResult:
        """Run a single test case."""
        name = test["name"]
        method = test["method"]
        tool_name = test.get("tool_name")
        tool_args = test.get("tool_args", test.get("tool_args_template", {}))

        # Substitute session_id in tool_args if provided
        if session_id:
            tool_args_str = json.dumps(tool_args)
            if "{session_id}" in tool_args_str:
                tool_args = json.loads(tool_args_str.replace("{session_id}", session_id))

        # Handle template-based expectations
        expect_contains = test.get("expect_contains", test.get("expect_contains_template", []))
        if session_id and test.get("expect_contains_template"):
            expect_contains = [p.replace("{session_id}", session_id) for p in test["expect_contains_template"]]

        expect_not_contains = test.get("expect_not_contains", test.get("expect_not_contains_template", []))
        if session_id and test.get("expect_not_contains_template"):
            expect_not_contains = [p.replace("{session_id}", session_id) for p in test["expect_not_contains_template"]]

        timeout = test.get("timeout_seconds", 60)

        print(f"{Colors.YELLOW}Running: {name}{Colors.NC}")
        print(f"  Method: {method}")
        if tool_name:
            print(f"  Tool: {tool_name}")
        if tool_args:
            args_preview = json.dumps(tool_args)[:60]
            print(f"  Args: {args_preview}{'...' if len(json.dumps(tool_args)) > 60 else ''}")

        start_time = datetime.now()
        stdout, stderr, exit_code = self.run_mcp_method(method, tool_name, tool_args, timeout=timeout)
        duration = (datetime.now() - start_time).total_seconds()

        # Save output
        output_file = self.results_dir / f"{name}.json"
        with open(output_file, "w") as f:
            f.write(f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n")

        # Check result
        if exit_code != 0:
            print(f"  {Colors.RED}✗ FAILED{Colors.NC} (exit code: {exit_code}, {duration:.1f}s)")
            print(f"  Output saved to: {output_file}")
            if stderr:
                print(f"  Error: {stderr[:200]}")
            return TestResult(
                name=name,
                category=category,
                passed=False,
                duration_seconds=duration,
                output=stdout,
                error=stderr,
            )

        # Check expected patterns
        passed, found, missing = self.check_output(stdout, expect_contains, expect_not_contains)

        if passed:
            print(f"  {Colors.GREEN}✓ PASSED{Colors.NC} ({duration:.1f}s)")
        else:
            print(f"  {Colors.RED}✗ FAILED{Colors.NC} ({duration:.1f}s)")
            print(f"  Missing patterns: {missing}")
            print(f"  Output saved to: {output_file}")

        return TestResult(
            name=name,
            category=category,
            passed=passed,
            duration_seconds=duration,
            output=stdout,
            expected_found=found,
            expected_missing=missing,
        )

    def run_category(
        self,
        category: str,
        category_data: dict[str, Any],
        session_id: str | None = None,
    ) -> list[TestResult]:
        """Run all tests in a category."""
        results: list[TestResult] = []

        print(f"\n{Colors.BLUE}=== {category.upper()} Tests ==={Colors.NC}")
        print(f"{category_data.get('description', '')}\n")

        for test in category_data.get("tests", []):
            result = self.run_test(test, category, session_id)
            results.append(result)

        # Summary
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        print(f"\n{Colors.YELLOW}{category.title()} Summary:{Colors.NC} {passed} passed, {failed} failed\n")

        return results

    def run_all_tests(
        self,
        categories: list[str] | None = None,
        require_openroad: bool = False,
    ) -> int:
        """
        Run all specified test categories.

        Returns:
            Number of failed tests
        """
        if not self.check_prerequisites(require_openroad):
            return 1

        all_results: list[TestResult] = []
        session_id = f"test-cli-{os.getpid()}"

        # Determine which categories to run (filter out metadata keys)
        available_categories = [k for k, v in self.test_cases.items() if not k.startswith("$") and isinstance(v, dict)]
        if categories:
            cats_to_run = [c for c in categories if c in available_categories]
        else:
            # Default: run discovery and error_handling (no OpenROAD required)
            cats_to_run = ["discovery", "error_handling"]
            if require_openroad:
                cats_to_run.extend(["session", "report_images"])

        for cat in cats_to_run:
            if cat not in self.test_cases:
                print(f"{Colors.YELLOW}Skipping unknown category: {cat}{Colors.NC}")
                continue

            cat_data = self.test_cases[cat]

            # Check requirements
            requires = cat_data.get("requires", [])
            if "openroad" in requires and not require_openroad:
                print(f"{Colors.YELLOW}Skipping {cat} (requires OpenROAD){Colors.NC}")
                continue

            results = self.run_category(cat, cat_data, session_id)
            all_results.extend(results)

        # Final summary
        total_passed = sum(1 for r in all_results if r.passed)
        total_failed = len(all_results) - total_passed

        print("\n" + "=" * 40)
        if total_failed == 0:
            print(f"{Colors.GREEN}All tests passed!{Colors.NC}")
        else:
            print(f"{Colors.RED}{total_failed} test(s) failed.{Colors.NC}")
        print(f"Results saved to: {self.results_dir}")

        # Write JSON report
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(all_results),
            "passed": total_passed,
            "failed": total_failed,
            "results": [
                {
                    "name": r.name,
                    "category": r.category,
                    "passed": r.passed,
                    "duration_seconds": r.duration_seconds,
                    "error": r.error,
                    "expected_missing": r.expected_missing,
                }
                for r in all_results
            ],
        }
        report_file = self.results_dir / "report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"JSON report: {report_file}")

        return total_failed

    def list_tests(self) -> None:
        """List all available tests."""
        print("Available test categories and tests:\n")
        for cat, data in self.test_cases.items():
            # Skip metadata keys like $schema, title, etc.
            if cat.startswith("$") or not isinstance(data, dict):
                continue
            requires = data.get("requires", [])
            req_str = f" (requires: {', '.join(requires)})" if requires else ""
            print(f"{Colors.BLUE}{cat}:{Colors.NC}{req_str}")
            for test in data.get("tests", []):
                print(f"  - {test['name']}: {test.get('description', '')}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MCP integration tests using MCP Inspector CLI")
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Run all tests including session tests (requires OpenROAD)",
    )
    parser.add_argument(
        "--category",
        "-c",
        action="append",
        help="Run specific category (can be specified multiple times)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available tests",
    )
    parser.add_argument(
        "--mcp-config",
        type=Path,
        default=Path(".mcp.json"),
        help="Path to MCP config file",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )

    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Find test cases file
    script_dir = Path(__file__).parent
    test_cases_file = script_dir / "test_cases.json"

    if not test_cases_file.exists():
        print(f"Error: test_cases.json not found at {test_cases_file}")
        return 1

    runner = MCPTestRunner(
        mcp_config=args.mcp_config,
        test_cases_file=test_cases_file,
    )

    if args.list:
        runner.list_tests()
        return 0

    return runner.run_all_tests(
        categories=args.category,
        require_openroad=args.all,
    )


if __name__ == "__main__":
    sys.exit(main())
