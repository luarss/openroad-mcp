"""MCP-based timing analysis demo for ORFS GCD design

This script demonstrates intelligent timing analysis using the OpenROAD MCP server
with the timing tools implemented in TICKET-011-MVP.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from openroad_mcp.core.manager import OpenROADManager


class ORFSTimingDemo:
    """Timing analysis demo using OpenROAD MCP timing tools"""

    def __init__(self, flow_home: str | None = None):
        self.flow_home = Path(flow_home) if flow_home else Path(os.getenv("FLOW_HOME", "."))
        self.manager = OpenROADManager()
        self.session_id: str | None = None
        self.design_name = "gcd"

        self.platform_path = self.flow_home / "platforms/nangate45"
        self.design_path = self.flow_home / "designs/nangate45/gcd"

        self.liberty_file = self.platform_path / "lib/NangateOpenCellLibrary_typical.lib"
        self.tech_lef = self.platform_path / "lef/NangateOpenCellLibrary.tech.lef"
        self.macro_lef = self.platform_path / "lef/NangateOpenCellLibrary.macro.lef"

    async def setup_session(self, verilog_path: Path, sdc_path: Path) -> dict[str, Any]:
        """Set up OpenROAD session with design files

        Args:
            verilog_path: Path to synthesized verilog
            sdc_path: Path to SDC constraints

        Returns:
            Dictionary with setup status and info
        """
        if not self.liberty_file.exists():
            return {
                "success": False,
                "error": f"Liberty file not found: {self.liberty_file}",
                "message": "Ensure FLOW_HOME points to OpenROAD-flow-scripts",
            }

        if not verilog_path.exists():
            return {"success": False, "error": f"Verilog file not found: {verilog_path}"}

        if not sdc_path.exists():
            return {"success": False, "error": f"SDC file not found: {sdc_path}"}

        self.session_id = await self.manager.create_session()
        session = self.manager._sessions[self.session_id]

        await session.send_command(f"read_liberty {self.liberty_file}")
        await session.read_output(timeout_ms=10000)

        await session.send_command(f"read_lef {self.tech_lef}")
        await session.read_output(timeout_ms=5000)

        await session.send_command(f"read_lef {self.macro_lef}")
        await session.read_output(timeout_ms=5000)

        await session.send_command(f"read_verilog {verilog_path}")
        await session.read_output(timeout_ms=5000)

        await session.send_command(f"link_design {self.design_name}")
        result = await session.read_output(timeout_ms=3000)

        if result.error:
            return {"success": False, "error": result.error, "message": "Failed to link design"}

        await session.send_command(f"read_sdc {sdc_path}")
        sdc_result = await session.read_output(timeout_ms=3000)

        if sdc_result.error:
            return {"success": False, "error": sdc_result.error, "message": "Failed to read SDC"}

        return {
            "success": True,
            "session_id": self.session_id,
            "design": self.design_name,
            "verilog": str(verilog_path),
            "sdc": str(sdc_path),
            "message": "Design loaded successfully",
        }

    async def analyze_violations(self) -> dict[str, Any]:
        """Analyze timing violations and categorize them

        Returns:
            Dictionary with violation analysis results
        """
        if not self.session_id:
            return {"error": "Session not initialized. Call setup_session() first"}

        session = self.manager._sessions[self.session_id]

        await session.send_command("report_wns")
        wns_result = await session.read_output(timeout_ms=5000)

        await session.send_command("report_tns")
        tns_result = await session.read_output(timeout_ms=5000)

        from openroad_mcp.timing.parsers import BasicTimingParser

        wns_data = BasicTimingParser.parse_wns_tns(wns_result.output, "report_wns")
        tns_data = BasicTimingParser.parse_wns_tns(tns_result.output, "report_tns")

        wns = wns_data.get("value")
        tns = tns_data.get("value")

        has_violations = wns is not None and wns < 0

        analysis = {
            "wns": wns,
            "tns": tns,
            "has_violations": has_violations,
            "severity": self._categorize_severity(wns, tns),
            "message": self._generate_violation_message(wns, tns),
        }

        if has_violations:
            await session.send_command("report_checks -path_delay max -format full_clock_expanded")
            paths_result = await session.read_output(timeout_ms=10000)

            paths = BasicTimingParser.parse_report_checks(paths_result.output)
            analysis["critical_paths"] = len(paths)
            analysis["worst_path"] = paths[0].model_dump() if paths else None

        return analysis

    async def examine_paths(self, num_paths: int = 5) -> dict[str, Any]:
        """Examine critical timing paths in detail

        Args:
            num_paths: Number of paths to analyze

        Returns:
            Dictionary with detailed path analysis
        """
        if not self.session_id:
            return {"error": "Session not initialized. Call setup_session() first"}

        session = self.manager._sessions[self.session_id]

        await session.send_command(
            f"report_checks -path_delay max -format full_clock_expanded -path_group **all** -path_count {num_paths}"
        )
        result = await session.read_output(timeout_ms=15000)

        from openroad_mcp.timing.parsers import BasicTimingParser

        paths = BasicTimingParser.parse_report_checks(result.output)

        return {
            "total_paths": len(paths),
            "paths": [p.model_dump() for p in paths],
            "analysis": self._analyze_path_characteristics(paths),
        }

    async def suggest_fixes(self, violation_analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate optimization suggestions based on violation analysis

        Args:
            violation_analysis: Results from analyze_violations()

        Returns:
            Dictionary with fix suggestions
        """
        if not violation_analysis.get("has_violations"):
            return {"message": "No violations found. Design meets timing!", "suggestions": []}

        wns = violation_analysis.get("wns", 0)
        tns = violation_analysis.get("tns", 0)

        suggestions = []

        if wns < -0.5:
            suggestions.append(
                {
                    "category": "clock_period",
                    "severity": "high",
                    "description": "Large WNS violation suggests clock period is too aggressive",
                    "action": "Increase clock period in SDC constraints",
                    "expected_improvement": f"~{abs(wns):.2f}ns improvement",
                }
            )

        if tns < -10:
            suggestions.append(
                {
                    "category": "fanout",
                    "severity": "medium",
                    "description": "High TNS indicates many failing paths, possibly due to high fanout",
                    "action": "Apply buffer insertion and fanout optimization",
                    "expected_improvement": "Reduce path count by 30-50%",
                }
            )

        if violation_analysis.get("critical_paths", 0) > 20:
            suggestions.append(
                {
                    "category": "placement",
                    "severity": "medium",
                    "description": "Many critical paths suggest placement optimization needed",
                    "action": "Adjust placement constraints or run incremental placement",
                    "expected_improvement": "10-20% WNS improvement",
                }
            )

        suggestions.append(
            {
                "category": "constraints",
                "severity": "low",
                "description": "Review timing exceptions and false paths",
                "action": "Add set_false_path or set_multicycle_path where appropriate",
                "expected_improvement": "Eliminate 5-10% of violations",
            }
        )

        return {"suggestions": suggestions, "total_suggestions": len(suggestions)}

    async def apply_fixes(self, sdc_path: Path, new_clock_period: float) -> dict[str, Any]:
        """Apply constraint fixes by modifying SDC file

        Args:
            sdc_path: Path to SDC file to modify
            new_clock_period: New clock period in nanoseconds

        Returns:
            Dictionary with fix application status
        """
        if not sdc_path.exists():
            return {"success": False, "error": f"SDC file not found: {sdc_path}"}

        backup_path = sdc_path.with_suffix(".sdc.backup")
        sdc_path.rename(backup_path)

        with open(backup_path) as f:
            content = f.read()

        import re

        new_content = re.sub(
            r"create_clock.*-period\s+[\d.]+",
            f"create_clock -period {new_clock_period}",
            content,
        )

        with open(sdc_path, "w") as f:
            f.write(new_content)

        return {
            "success": True,
            "backup_file": str(backup_path),
            "new_clock_period": new_clock_period,
            "message": f"Updated clock period to {new_clock_period}ns",
        }

    async def verify_closure(self) -> dict[str, Any]:
        """Verify timing closure after fixes

        Returns:
            Dictionary with closure verification results
        """
        analysis = await self.analyze_violations()

        is_closed = not analysis.get("has_violations", True)

        return {
            "timing_closed": is_closed,
            "wns": analysis.get("wns"),
            "tns": analysis.get("tns"),
            "message": "Timing closed!" if is_closed else "Timing violations remain",
            "analysis": analysis,
        }

    async def cleanup(self):
        """Clean up resources"""
        if self.session_id:
            await self.manager.cleanup_all()

    def _categorize_severity(self, wns: float | None, tns: float | None) -> str:
        """Categorize violation severity"""
        if wns is None or wns >= 0:
            return "none"
        if wns < -1.0:
            return "critical"
        if wns < -0.5:
            return "high"
        if wns < -0.1:
            return "medium"
        return "low"

    def _generate_violation_message(self, wns: float | None, tns: float | None) -> str:
        """Generate human-readable violation message"""
        if wns is None:
            return "Unable to determine timing status"
        if wns >= 0:
            return f"Design meets timing with {wns:.2f}ns slack"
        if tns is not None:
            return f"Timing violations: WNS={wns:.2f}ns, TNS={tns:.2f}ns"
        return f"Timing violations: WNS={wns:.2f}ns"

    def _analyze_path_characteristics(self, paths: list) -> dict[str, Any]:
        """Analyze common characteristics across paths"""
        if not paths:
            return {}

        path_groups = {}
        for path in paths:
            group = path.path_group
            if group not in path_groups:
                path_groups[group] = []
            path_groups[group].append(path)

        return {
            "path_groups": list(path_groups.keys()),
            "group_counts": {g: len(p) for g, p in path_groups.items()},
            "avg_slack": sum(p.slack for p in paths) / len(paths) if paths else 0,
        }


async def main():
    """Demo entry point"""
    flow_home = os.getenv("FLOW_HOME", "/home/luars/OpenROAD-flow-scripts/flow")

    demo = ORFSTimingDemo(flow_home)

    verilog = Path(flow_home) / "results/nangate45/gcd/base/1_synth.v"
    sdc = Path(flow_home) / "designs/nangate45/gcd/constraint.sdc"

    print("Setting up timing analysis session...")
    setup_result = await demo.setup_session(verilog, sdc)
    print(f"Setup: {setup_result['message']}")

    if not setup_result["success"]:
        print(f"Error: {setup_result['error']}")
        return

    print("\nAnalyzing violations...")
    violations = await demo.analyze_violations()
    print(f"WNS: {violations['wns']}, TNS: {violations['tns']}")
    print(f"Severity: {violations['severity']}")
    print(f"Message: {violations['message']}")

    if violations["has_violations"]:
        print("\nExamining critical paths...")
        paths = await demo.examine_paths(num_paths=3)
        print(f"Found {paths['total_paths']} critical paths")

        print("\nGenerating fix suggestions...")
        suggestions = await demo.suggest_fixes(violations)
        for i, sug in enumerate(suggestions["suggestions"], 1):
            print(f"\n{i}. {sug['category'].upper()} ({sug['severity']})")
            print(f"   {sug['description']}")
            print(f"   Action: {sug['action']}")

    await demo.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
