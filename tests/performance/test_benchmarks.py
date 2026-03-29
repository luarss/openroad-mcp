"""Performance benchmark tests for interactive shell functionality.

Uses real OpenROAD processes — no mocks. Runs in Docker CI via `make test-performance`.
"""

import asyncio
import time

import pytest

from openroad_mcp.core.manager import OpenROADManager as SessionManager
from openroad_mcp.interactive.buffer import CircularBuffer


@pytest.mark.asyncio
class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def benchmark_timeout(self):
        """Timeout for benchmark tests."""
        return 10.0  # 10 seconds max

    async def test_session_creation_latency(self, benchmark_timeout):
        """Test session creation latency benchmark with real processes."""
        session_manager = SessionManager()
        creation_times = []

        try:
            for _i in range(5):
                start_time = time.perf_counter()
                await session_manager.create_session()
                end_time = time.perf_counter()

                creation_time = end_time - start_time
                creation_times.append(creation_time)

            avg_time = sum(creation_times) / len(creation_times)
            max_time = max(creation_times)
            min_time = min(creation_times)

            print("Session Creation Performance (real OpenROAD):")
            print(f"  Average: {avg_time * 1000:.2f}ms")
            print(f"  Min: {min_time * 1000:.2f}ms")
            print(f"  Max: {max_time * 1000:.2f}ms")

            # Real process spawning budget — much more generous than the old mocked 50ms
            assert avg_time < 5.0, f"Average creation time {avg_time:.3f}s exceeds 5s target"
            assert max_time < 10.0, f"Max creation time {max_time:.3f}s exceeds 10s limit"

        finally:
            await session_manager.cleanup_all()

    async def test_output_streaming_throughput(self, benchmark_timeout):
        """Test output streaming throughput."""
        buffer = CircularBuffer(max_size=10 * 1024 * 1024)  # 10MB buffer

        chunk_size = 1024  # 1KB chunks
        total_chunks = 1000  # 1MB total
        test_data = b"x" * chunk_size

        start_time = time.perf_counter()

        for _i in range(total_chunks):
            await buffer.append(test_data)

        chunks = await buffer.drain_all()
        end_time = time.perf_counter()

        total_bytes = len(chunks) * chunk_size
        duration = end_time - start_time
        throughput_mbps = (total_bytes / (1024 * 1024)) / duration

        print("Output Streaming Performance:")
        print(f"  Total data: {total_bytes / (1024 * 1024):.2f}MB")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Throughput: {throughput_mbps:.2f}MB/s")

        assert throughput_mbps > 10, f"Throughput {throughput_mbps:.2f}MB/s is below 10MB/s minimum"
        assert duration < 5.0, f"Streaming took {duration:.3f}s (>5s timeout)"

    async def test_memory_usage_profiling(self, benchmark_timeout):
        """Test memory usage profiling."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        session_manager = SessionManager()

        try:
            session_count = 5
            buffer_size = 1024 * 1024  # 1MB each

            for _i in range(session_count):
                session_id = await session_manager.create_session(buffer_size=buffer_size)

                session = session_manager._sessions[session_id]
                test_data = b"x" * (buffer_size // 10)  # Fill 10% of buffer
                for _j in range(10):
                    await session.output_buffer.append(test_data)

            mid_memory = process.memory_info().rss / (1024 * 1024)  # MB
            memory_increase = mid_memory - initial_memory

            print("Memory Usage Profiling:")
            print(f"  Initial memory: {initial_memory:.2f}MB")
            print(f"  After allocation: {mid_memory:.2f}MB")
            print(f"  Memory increase: {memory_increase:.2f}MB")
            print(f"  Per session: {memory_increase / session_count:.2f}MB")

            await session_manager.cleanup_all()

            await asyncio.sleep(0.1)

            final_memory = process.memory_info().rss / (1024 * 1024)  # MB
            memory_leaked = final_memory - initial_memory

            print(f"  After cleanup: {final_memory:.2f}MB")
            print(f"  Memory leaked: {memory_leaked:.2f}MB")

            expected_memory = session_count * (buffer_size / (1024 * 1024))  # Expected MB
            assert memory_increase < expected_memory * 2, f"Memory usage {memory_increase:.2f}MB exceeds 2x expected"
            assert memory_leaked < 50, f"Memory leak {memory_leaked:.2f}MB exceeds 50MB threshold"

        finally:
            await session_manager.cleanup_all()

    async def test_buffer_overflow_performance(self, benchmark_timeout):
        """Test buffer overflow and eviction performance."""
        buffer_size = 1024 * 1024  # 1MB buffer
        buffer = CircularBuffer(max_size=buffer_size)

        chunk_size = 1024  # 1KB chunks
        chunks_to_overflow = (buffer_size // chunk_size) * 2  # 2x overflow
        test_chunk = b"x" * chunk_size

        start_time = time.perf_counter()

        for i in range(chunks_to_overflow):
            await buffer.append(test_chunk)

            if i % 100 == 0:
                current_size = await buffer.get_size()
                assert current_size <= buffer_size * 1.1, f"Buffer size {current_size} exceeds limit"

        chunks = await buffer.drain_all()
        end_time = time.perf_counter()

        duration = end_time - start_time
        operations_per_sec = chunks_to_overflow / duration

        print("Buffer Overflow Performance:")
        print(f"  Operations: {chunks_to_overflow}")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Rate: {operations_per_sec:.0f} ops/sec")
        print(f"  Final chunks: {len(chunks)}")

        assert operations_per_sec > 1000, f"Operation rate {operations_per_sec:.0f} ops/sec is too low"
        assert duration < 5.0, f"Overflow test took {duration:.3f}s (>5s)"

        final_size = sum(len(chunk) for chunk in chunks)
        assert final_size <= buffer_size, f"Final buffer size {final_size} exceeds limit {buffer_size}"


@pytest.mark.asyncio
class TestStressTests:
    """Stress tests for interactive shell functionality."""

    async def test_resource_exhaustion_handling(self):
        """Test handling of resource exhaustion scenarios."""
        session_manager = SessionManager()

        try:
            max_sessions = 20  # Conservative for real processes

            session_ids = []

            for i in range(max_sessions):
                try:
                    session_id = await session_manager.create_session()
                    session_ids.append(session_id)
                except Exception as e:
                    print(f"Resource limit reached at {i} sessions: {e}")
                    break

            print(f"Created {len(session_ids)} sessions before resource exhaustion")

            assert len(session_ids) >= 5, "Should support at least 5 concurrent sessions"

            cleanup_start = time.perf_counter()
            await session_manager.cleanup_all()
            cleanup_time = time.perf_counter() - cleanup_start

            print(f"Cleanup completed in {cleanup_time:.3f}s")
            assert cleanup_time < 30.0, f"Cleanup took {cleanup_time:.3f}s (>30s)"

        finally:
            await session_manager.cleanup_all()

    async def test_large_output_handling(self):
        """Test handling of large output data."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session()

            session = session_manager._sessions[session_id]

            chunk_size = 16 * 1024  # 16KB chunks
            chunk = b"x" * chunk_size
            total_written = 0

            start_time = time.perf_counter()

            for _i in range(320):  # 320 * 16KB = 5MB
                await session.output_buffer.append(chunk)
                total_written += chunk_size

            chunks = await session.output_buffer.drain_all()
            buffer_size = sum(len(chunk) for chunk in chunks)

            end_time = time.perf_counter()
            duration = end_time - start_time

            print("Large Output Handling:")
            print(f"  Total written: {total_written / (1024 * 1024):.2f}MB")
            print(f"  Buffer size: {buffer_size / 1024:.2f}KB")
            print(f"  Duration: {duration:.3f}s")
            print(f"  Throughput: {(total_written / (1024 * 1024)) / duration:.2f}MB/s")

            assert 100 * 1024 <= buffer_size <= 150 * 1024, f"Buffer size {buffer_size} not within expected range"
            assert duration < 2.0, f"Large output handling took {duration:.3f}s (>2s)"
            assert total_written >= 5 * 1024 * 1024, "Should have written at least 5MB of data"

        finally:
            await session_manager.cleanup_all()


if __name__ == "__main__":
    # Allow running benchmarks directly
    pytest.main([__file__, "-v", "-s"])
