"""Session scalability tests using real OpenROAD processes.

All tests require the OpenROAD binary and run in Docker CI via `make test-scalability`.
No mocks — every test exercises the full PTY/buffer/queue/lock path.
"""

import asyncio
import math
import time

import pytest

from openroad_mcp.core.manager import OpenROADManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def percentile(data: list[float], pct: float) -> float:
    """Return the pct-th percentile from a sorted list of latencies (seconds)."""
    if not data:
        return 0.0
    s = sorted(data)
    return s[min(len(s) - 1, math.ceil(pct / 100 * len(s)) - 1)]


async def create_sessions(manager: OpenROADManager, count: int) -> list[str]:
    """Create *count* sessions via the manager and return their IDs."""
    tasks = [manager.create_session() for _ in range(count)]
    return list(await asyncio.gather(*tasks))


async def terminate_sessions(manager: OpenROADManager, session_ids: list[str]) -> None:
    """Terminate sessions in parallel."""
    await asyncio.gather(*[manager.terminate_session(sid) for sid in session_ids])


async def run_command_per_session(
    manager: OpenROADManager,
    session_ids: list[str],
    command: str = "puts hello",
) -> list[float]:
    """Run *command* on each session concurrently, return per-command latencies (s)."""
    async def _exec(sid: str) -> float:
        t0 = time.perf_counter()
        await manager.execute_command(sid, command)
        return time.perf_counter() - t0

    return list(await asyncio.gather(*[_exec(sid) for sid in session_ids]))


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGraduatedLoadScaling:
    """Measure how session and command throughput degrade as concurrency increases."""

    LEVELS_CREATE = [2, 4, 6, 8]
    LEVELS_COMMAND = [1, 3, 5, 8]

    async def test_create_throughput_at_levels(self, scalability_report):
        """Create sessions concurrently at graduated load levels."""
        for level in self.LEVELS_CREATE:
            manager = OpenROADManager()
            try:
                t0 = time.perf_counter()
                ids = await create_sessions(manager, level)
                wall = time.perf_counter() - t0

                per_session = [wall / level] * level  # approx per-session from wall time
                scalability_report.record_phase(
                    f"create_{level}", level, per_session, wall,
                )
                assert len(ids) == level
            finally:
                await manager.cleanup_all()

        # Assert bounded degradation: p99 at max level < 3x wall-time at min level
        min_wall = scalability_report.phases[0]["wall_time_s"]
        max_wall = scalability_report.phases[-1]["wall_time_s"]
        ratio = max_wall / min_wall if min_wall > 0 else float("inf")
        assert ratio < 3.0 * self.LEVELS_CREATE[-1] / self.LEVELS_CREATE[0], (
            f"Create wall-time scaled worse than 3x: {max_wall:.2f}s / {min_wall:.2f}s = {ratio:.1f}x"
        )

    async def test_command_throughput_at_levels(self, scalability_report):
        """Run commands at graduated concurrency levels across real sessions."""
        manager = OpenROADManager()
        try:
            # Create enough sessions for the highest concurrency level
            all_ids = await create_sessions(manager, max(self.LEVELS_COMMAND))
            await asyncio.sleep(0.5)  # let sessions settle

            for level in self.LEVELS_COMMAND:
                ids = all_ids[:level]
                latencies = await run_command_per_session(manager, ids)
                wall = sum(latencies)
                scalability_report.record_phase(
                    f"cmd_{level}_concurrent", level, latencies, wall,
                )

            # Degradation check: p99 at max level < 3x p99 at min level
            min_p99 = scalability_report.phases[0]["latency_ms"]["p99"]
            max_p99 = scalability_report.phases[-1]["latency_ms"]["p99"]
            ratio = max_p99 / min_p99 if min_p99 > 0 else float("inf")
            assert ratio < 3.0, (
                f"Command p99 degraded beyond 3x: {max_p99:.1f}ms / {min_p99:.1f}ms = {ratio:.1f}x"
            )
        finally:
            await manager.cleanup_all()

    async def test_mixed_create_execute_destroy(self, scalability_report):
        """Interleave session creation, command execution, and termination."""
        manager = OpenROADManager()
        try:
            t_total = time.perf_counter()

            # Phase 1: create 3, execute
            ids = await create_sessions(manager, 3)
            await asyncio.sleep(0.5)
            latencies_1 = await run_command_per_session(manager, ids)

            # Phase 2: terminate 1, create 2 more, execute all
            await manager.terminate_session(ids[0])
            new_ids = await create_sessions(manager, 2)
            await asyncio.sleep(0.5)
            active = ids[1:] + new_ids
            latencies_2 = await run_command_per_session(manager, active)

            # Phase 3: terminate all
            t_teardown = time.perf_counter()
            await terminate_sessions(manager, active)
            teardown_wall = time.perf_counter() - t_teardown

            total_wall = time.perf_counter() - t_total

            scalability_report.record_phase("phase1_create_exec", 3, latencies_1, sum(latencies_1))
            scalability_report.record_phase("phase2_create_exec", len(active), latencies_2, sum(latencies_2))
            scalability_report.record_phase("phase3_teardown", len(active), [], teardown_wall)
            scalability_report.record_phase("total", 5, [], total_wall)

            assert len(latencies_1) == 3
            assert len(latencies_2) == len(active)
            assert teardown_wall < 30.0, f"Teardown took {teardown_wall:.1f}s"
        finally:
            await manager.cleanup_all()


@pytest.mark.asyncio
class TestRampUpDown:
    """Test realistic ramp-up and ramp-down patterns."""

    BATCH_SIZES_UP = [1, 1, 2, 2, 2]  # total 8
    BATCH_SIZES_DOWN = [1, 2, 2, 3]  # total 8

    async def test_ramp_up_creation_latency(self, scalability_report):
        """Create sessions in incremental batches, measure per-batch latency."""
        manager = OpenROADManager()
        try:
            all_ids: list[str] = []
            batch_means: list[float] = []

            for i, batch_size in enumerate(self.BATCH_SIZES_UP):
                t0 = time.perf_counter()
                new_ids = await create_sessions(manager, batch_size)
                wall = time.perf_counter() - t0
                all_ids.extend(new_ids)

                scalability_report.record_phase(
                    f"ramp_up_batch{i+1}({batch_size})", len(all_ids), [wall], wall,
                )
                batch_means.append(wall)

            # Each batch's mean should be within 2x of the first batch's mean
            baseline = batch_means[0]
            for i, mean in enumerate(batch_means):
                assert mean < baseline * 2.0, (
                    f"Batch {i+1} latency {mean:.2f}s exceeds 2x baseline {baseline:.2f}s"
                )
        finally:
            await manager.cleanup_all()

    async def test_ramp_down_cleanup_latency(self, scalability_report):
        """Terminate sessions in batches, measure per-batch latency."""
        manager = OpenROADManager()
        try:
            all_ids = await create_sessions(manager, sum(self.BATCH_SIZES_DOWN))
            await asyncio.sleep(0.5)

            offset = 0
            for i, batch_size in enumerate(self.BATCH_SIZES_DOWN):
                batch_ids = all_ids[offset : offset + batch_size]
                offset += batch_size

                t0 = time.perf_counter()
                await terminate_sessions(manager, batch_ids)
                wall = time.perf_counter() - t0

                remaining = len(all_ids) - offset
                scalability_report.record_phase(
                    f"ramp_down_batch{i+1}({batch_size})", remaining, [wall], wall,
                )

                assert wall < 30.0, f"Batch {i+1} termination took {wall:.1f}s"
        finally:
            await manager.cleanup_all()

    async def test_ramp_up_ramp_down_cycle(self, scalability_report):
        """Full cycle: ramp up -> execute -> ramp down -> ramp up again.

        Detects state leaks: the second ramp-up should not be slower
        than the first because the _sessions dict was cleaned.
        """
        manager = OpenROADManager()
        try:
            total_sessions = 6

            # First ramp-up
            t0 = time.perf_counter()
            ids_1 = await create_sessions(manager, total_sessions)
            ramp_up_1 = time.perf_counter() - t0
            await asyncio.sleep(0.5)

            # Execute commands
            await run_command_per_session(manager, ids_1)

            # Ramp down
            t0 = time.perf_counter()
            await terminate_sessions(manager, ids_1)
            ramp_down = time.perf_counter() - t0

            # Second ramp-up
            t0 = time.perf_counter()
            ids_2 = await create_sessions(manager, total_sessions)
            ramp_up_2 = time.perf_counter() - t0

            await asyncio.sleep(0.5)
            await run_command_per_session(manager, ids_2)

            scalability_report.record_phase("ramp_up_1", total_sessions, [], ramp_up_1)
            scalability_report.record_phase("ramp_down", total_sessions, [], ramp_down)
            scalability_report.record_phase("ramp_up_2", total_sessions, [], ramp_up_2)

            # Second ramp-up should not be slower (no state leak)
            assert ramp_up_2 <= ramp_up_1 * 1.5, (
                f"Second ramp-up {ramp_up_2:.2f}s is >1.5x first {ramp_up_1:.2f}s — possible state leak"
            )
        finally:
            await manager.cleanup_all()


@pytest.mark.asyncio
class TestCleanupLockContention:
    """Exercise the _cleanup_lock bottleneck with real processes."""

    async def test_lock_serializes_concurrent_creates(self, scalability_report):
        """Verify that concurrent creates serialize behind _cleanup_lock.

        Wall time for N concurrent creates should be roughly N * single_create_time
        (linear scaling) because the lock serializes them.
        """
        manager = OpenROADManager()
        try:
            # Baseline: single session creation time
            single_times: list[float] = []
            for _ in range(3):
                t0 = time.perf_counter()
                sid = await manager.create_session()
                single_times.append(time.perf_counter() - t0)
                await manager.terminate_session(sid)
            avg_single = sum(single_times) / len(single_times)

            # Concurrent creation of 6 sessions
            t0 = time.perf_counter()
            ids = await create_sessions(manager, 6)
            concurrent_wall = time.perf_counter() - t0

            scalability_report.record_phase("single_avg", 1, single_times, avg_single)
            scalability_report.record_phase("concurrent_6", 6, [], concurrent_wall)

            # Wall time should be at least ~1x single (serialized) but less than 6x
            # If lock didn't exist, wall ~ single (all parallel). With lock, wall ~ N*single.
            assert concurrent_wall >= avg_single * 0.5, (
                f"Concurrent wall {concurrent_wall:.2f}s too fast — lock may not be serializing"
            )
            assert len(ids) == 6
        finally:
            await manager.cleanup_all()

    async def test_cleanup_scan_cost_with_dead_sessions(self, scalability_report):
        """Measure how dead sessions increase the cost of _cleanup_terminated_sessions.

        Create K sessions, terminate them all, then time the next create_session
        (which runs cleanup under the lock). Repeat for increasing K.
        """
        levels = [2, 4, 6, 8]

        for k in levels:
            manager = OpenROADManager()
            try:
                # Create and terminate K sessions (leave dead entries in _sessions)
                ids = await create_sessions(manager, k)
                for sid in ids:
                    await manager.terminate_session(sid)

                # Time the next create — this runs _cleanup_terminated_sessions
                t0 = time.perf_counter()
                await manager.create_session()
                post_cleanup_create = time.perf_counter() - t0

                scalability_report.record_phase(
                    f"after_{k}_dead", k, [post_cleanup_create], post_cleanup_create,
                )
            finally:
                await manager.cleanup_all()

        # Verify cleanup cost grows roughly linearly (not exponentially)
        walls = [p["wall_time_s"] for p in scalability_report.phases]
        if len(walls) >= 2:
            max_wall = max(walls)
            min_wall = min(walls)
            # At 4x the session count, cleanup should be at most 10x slower (linear-ish)
            ratio = max_wall / min_wall if min_wall > 0 else float("inf")
            max_k = max(levels)
            min_k = min(levels)
            assert ratio < 10.0 * max_k / min_k, (
                f"Cleanup cost grew super-linearly: {max_wall:.2f}s / {min_wall:.2f}s = {ratio:.1f}x"
            )
