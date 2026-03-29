"""Shared fixtures for performance and scalability tests."""

import gc
import json
import math
import warnings

import pytest


class ScalabilityReport:
    """Collects and formats scalability metrics for CI comparison."""

    def __init__(self):
        self.phases: list[dict] = []

    def record_phase(self, phase_name: str, session_count: int, latencies: list[float], wall_time: float) -> dict:
        """Record metrics for a test phase."""
        if not latencies:
            entry = {
                "phase": phase_name,
                "session_count": session_count,
                "wall_time_s": round(wall_time, 3),
                "operations": 0,
            }
            self.phases.append(entry)
            return entry

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        entry = {
            "phase": phase_name,
            "session_count": session_count,
            "wall_time_s": round(wall_time, 3),
            "operations": n,
            "throughput_ops_per_sec": round(n / wall_time, 1) if wall_time > 0 else 0,
            "latency_ms": {
                "min": round(sorted_lat[0] * 1000, 2),
                "mean": round(sum(sorted_lat) / n * 1000, 2),
                "p50": round(sorted_lat[n // 2] * 1000, 2),
                "p95": round(sorted_lat[min(n - 1, math.ceil(0.95 * n) - 1)] * 1000, 2),
                "p99": round(sorted_lat[min(n - 1, math.ceil(0.99 * n) - 1)] * 1000, 2),
                "max": round(sorted_lat[-1] * 1000, 2),
            },
        }
        self.phases.append(entry)
        return entry

    def format_table(self) -> str:
        """Format all phases as a comparison table."""
        lines = ["\nScalability Report:", "-" * 80]
        lines.append(f"{'Phase':<30} {'N':>4} {'Wall(s)':>8} {'ops/s':>8} {'Mean':>8} {'p95':>8} {'p99':>8}")
        lines.append("-" * 80)
        for p in self.phases:
            lat = p.get("latency_ms", {})
            lines.append(
                f"{p['phase']:<30} {p['session_count']:>4} {p['wall_time_s']:>8.2f} "
                f"{p.get('throughput_ops_per_sec', 0):>8.1f} "
                f"{lat.get('mean', 0):>7.1f}ms "
                f"{lat.get('p95', 0):>7.1f}ms "
                f"{lat.get('p99', 0):>7.1f}ms"
            )
        lines.append("-" * 80)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize report for machine parsing."""
        return json.dumps({"phases": self.phases}, indent=2)


@pytest.fixture
def scalability_report():
    """Provide a ScalabilityReport that auto-prints on teardown."""
    report = ScalabilityReport()
    yield report
    print(report.format_table())
    print(report.to_json())


@pytest.fixture(autouse=True)
async def reset_manager():
    """Reset OpenROADManager singleton between tests."""
    from openroad_mcp.core.manager import OpenROADManager

    OpenROADManager._instance = None

    yield

    instance = OpenROADManager._instance
    if instance is not None:
        try:
            await instance.cleanup_all()
        except Exception as e:
            warnings.warn(f"reset_manager teardown: cleanup_all() failed: {e}", stacklevel=2)
        OpenROADManager._instance = None

    gc.collect()
