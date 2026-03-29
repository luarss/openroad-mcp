"""
End-to-end latency benchmarks for OpenROAD MCP tool calls.

Requires a running OpenROAD binary (linux/amd64 only).
Runs automatically in CI via Dockerfile.test.

Addresses issue #42 question 2: "Are there any benchmarks for latency?"
"""

import asyncio
import time

import pytest

from openroad_mcp.core.manager import OpenROADManager


def percentile(data: list[float], pct: float) -> float:
    if not data:
        raise ValueError("Cannot compute percentile of an empty list")
    s = sorted(data)
    return s[min(int(len(s) * pct / 100), len(s) - 1)]


@pytest.mark.asyncio
async def test_create_session_latency() -> None:
    """Measure time to spawn an OpenROAD process."""
    manager = OpenROADManager()
    latencies = []
    try:
        for _ in range(5):
            t0 = time.perf_counter()
            session_id = await manager.create_session()
            latencies.append((time.perf_counter() - t0) * 1000)
            await manager.terminate_session(session_id)
        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        print(f"\ncreate_session: p50={p50:.1f}ms p95={p95:.1f}ms")
        assert p95 < 10000, f"Session spawn p95={p95:.1f}ms exceeds 10s budget"
    finally:
        await manager.cleanup_all()


@pytest.mark.asyncio
async def test_fast_command_latency() -> None:
    """Measure round-trip latency for a fast TCL command."""
    manager = OpenROADManager()
    try:
        session_id = await manager.create_session()
        await asyncio.sleep(0.5)  # Allow OpenROAD to finish startup
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            await manager.execute_command(session_id, "puts hello")
            latencies.append((time.perf_counter() - t0) * 1000)
        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        print(f"\nrun_tcl(puts): p50={p50:.1f}ms p95={p95:.1f}ms")
        assert p95 < 5000, f"p95={p95:.1f}ms exceeds 5s budget"
    finally:
        await manager.cleanup_all()


# ---------------------------------------------------------------------------
# Concurrent E2E tests (real OpenROAD, no mocks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_session_creation() -> None:
    """Create sessions concurrently at multiple levels, measure latency distribution."""
    manager = OpenROADManager()
    try:
        for level in [3, 5, 8]:
            t0 = time.perf_counter()
            ids = await asyncio.gather(*[manager.create_session() for _ in range(level)])
            wall = time.perf_counter() - t0

            assert len(ids) == level
            assert len(set(ids)) == level, "Duplicate session IDs"

            per_session_ms = (wall / level) * 1000
            print(f"\nconcurrent_create({level}): wall={wall:.2f}s  per_session={per_session_ms:.0f}ms")

            # Clean up before next level
            await asyncio.gather(*[manager.terminate_session(sid) for sid in ids])

        # If we got here, all levels succeeded
    finally:
        await manager.cleanup_all()


@pytest.mark.asyncio
async def test_concurrent_command_throughput() -> None:
    """5 sessions, 5 concurrent commands each, measure throughput."""
    manager = OpenROADManager()
    try:
        ids = await asyncio.gather(*[manager.create_session() for _ in range(5)])
        await asyncio.sleep(0.5)  # let OpenROAD start up

        all_latencies: list[float] = []

        # Run 5 rounds of concurrent commands
        for _round_num in range(5):
            async def _exec(sid: str) -> float:
                t0 = time.perf_counter()
                await manager.execute_command(sid, "puts hello")
                return (time.perf_counter() - t0) * 1000

            latencies = await asyncio.gather(*[_exec(sid) for sid in ids])
            all_latencies.extend(latencies)

        p50 = percentile(all_latencies, 50)
        p95 = percentile(all_latencies, 95)
        total_cmds = len(all_latencies)
        total_time = sum(all_latencies) / 1000  # back to seconds
        throughput = total_cmds / total_time if total_time > 0 else 0

        print("\nconcurrent_throughput(5 sessions x 5 rounds):")
        print(f"  Commands: {total_cmds}")
        print(f"  p50={p50:.1f}ms  p95={p95:.1f}ms")
        print(f"  Throughput: {throughput:.1f} cmds/sec")

        assert p95 < 30000, f"p95={p95:.1f}ms exceeds 30s budget"
    finally:
        await manager.cleanup_all()


@pytest.mark.asyncio
async def test_mixed_workload() -> None:
    """Mixed workload: long command + fast commands + idle + create/terminate, all concurrent.

    Verifies session isolation — no session's latency should be impacted by another's
    long-running command.
    """
    manager = OpenROADManager()
    try:
        # Create 4 sessions
        ids = await asyncio.gather(*[manager.create_session() for _ in range(4)])
        await asyncio.sleep(0.5)

        long_session, fast_session_1, fast_session_2, idle_session = ids

        results: dict[str, float] = {}

        async def run_long():
            t0 = time.perf_counter()
            await manager.execute_command(long_session, "after 1000; puts done")
            results["long"] = (time.perf_counter() - t0) * 1000

        async def run_fast(sid: str, label: str):
            t0 = time.perf_counter()
            await manager.execute_command(sid, "puts fast")
            results[label] = (time.perf_counter() - t0) * 1000

        async def idle_check():
            # Session exists but does nothing — just verify it's alive
            await asyncio.sleep(0.5)
            info = await manager.get_session_info(idle_session)
            assert info.is_alive

        # Run all concurrently
        await asyncio.gather(
            run_long(),
            run_fast(fast_session_1, "fast_1"),
            run_fast(fast_session_2, "fast_2"),
            idle_check(),
        )

        print("\nmixed_workload results:")
        for label, ms in results.items():
            print(f"  {label}: {ms:.1f}ms")

        # Fast commands should complete much faster than the long command
        # (verifying sessions are isolated from each other)
        assert results["fast_1"] < results["long"], (
            f"fast_1 ({results['fast_1']:.0f}ms) not faster than long ({results['long']:.0f}ms) — isolation failure"
        )
        assert results["fast_2"] < results["long"], (
            f"fast_2 ({results['fast_2']:.0f}ms) not faster than long ({results['long']:.0f}ms) — isolation failure"
        )

    finally:
        await manager.cleanup_all()
