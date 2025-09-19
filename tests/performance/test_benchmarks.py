"""Performance benchmark tests for interactive shell functionality."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from openroad_mcp.interactive.buffer import CircularBuffer
from openroad_mcp.interactive.session_manager import SessionManager


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""

    @pytest.fixture
    def benchmark_timeout(self):
        """Timeout for benchmark tests."""
        return 10.0  # 10 seconds max

    async def test_session_creation_latency(self, benchmark_timeout):
        """Test session creation latency benchmark."""
        session_manager = SessionManager()
        creation_times = []

        try:
            # Benchmark session creation
            for _i in range(10):
                start_time = time.perf_counter()
                await session_manager.create_session()
                end_time = time.perf_counter()

                creation_time = end_time - start_time
                creation_times.append(creation_time)

                # TICKET-020 requirement: <50ms session creation
                assert creation_time < 0.05, f"Session creation took {creation_time:.3f}s (>50ms)"

            # Calculate statistics
            avg_time = sum(creation_times) / len(creation_times)
            max_time = max(creation_times)
            min_time = min(creation_times)

            print("Session Creation Performance:")
            print(f"  Average: {avg_time * 1000:.2f}ms")
            print(f"  Min: {min_time * 1000:.2f}ms")
            print(f"  Max: {max_time * 1000:.2f}ms")

            # Performance assertions
            assert avg_time < 0.025, f"Average creation time {avg_time:.3f}s exceeds 25ms target"
            assert max_time < 0.05, f"Max creation time {max_time:.3f}s exceeds 50ms limit"

        finally:
            await session_manager.cleanup_all()

    async def test_output_streaming_throughput(self, benchmark_timeout):
        """Test output streaming throughput."""
        buffer = CircularBuffer(max_size=10 * 1024 * 1024)  # 10MB buffer

        # Generate test data
        chunk_size = 1024  # 1KB chunks
        total_chunks = 1000  # 1MB total
        test_data = b"x" * chunk_size

        start_time = time.perf_counter()

        # Stream data into buffer
        for _i in range(total_chunks):
            await buffer.append(test_data)

        # Drain all data
        chunks = await buffer.drain_all()
        end_time = time.perf_counter()

        # Calculate throughput
        total_bytes = len(chunks) * chunk_size
        duration = end_time - start_time
        throughput_mbps = (total_bytes / (1024 * 1024)) / duration

        print("Output Streaming Performance:")
        print(f"  Total data: {total_bytes / (1024 * 1024):.2f}MB")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Throughput: {throughput_mbps:.2f}MB/s")

        # Performance assertions
        assert throughput_mbps > 10, f"Throughput {throughput_mbps:.2f}MB/s is below 10MB/s minimum"
        assert duration < 5.0, f"Streaming took {duration:.3f}s (>5s timeout)"

    async def test_concurrent_session_scalability(self, benchmark_timeout):
        """Test concurrent session scalability."""
        session_manager = SessionManager()

        try:
            # TICKET-020 requirement: Support 20+ concurrent sessions
            concurrent_sessions = 25
            session_ids = []

            start_time = time.perf_counter()

            # Create sessions concurrently
            async def create_session_with_delay():
                await asyncio.sleep(0.001)  # Small delay to simulate real usage
                return await session_manager.create_session()

            tasks = [create_session_with_delay() for _ in range(concurrent_sessions)]
            session_ids = await asyncio.gather(*tasks)

            creation_time = time.perf_counter() - start_time

            print("Concurrent Session Creation:")
            print(f"  Sessions: {len(session_ids)}")
            print(f"  Duration: {creation_time:.3f}s")
            print(f"  Rate: {len(session_ids) / creation_time:.1f} sessions/sec")

            # Verify all sessions created successfully
            assert len(session_ids) == concurrent_sessions
            assert len(set(session_ids)) == concurrent_sessions  # All unique

            # Performance assertions
            assert creation_time < 5.0, f"Concurrent creation took {creation_time:.3f}s (>5s)"

            # Test concurrent operations
            start_time = time.perf_counter()

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):
                mock_read.return_value = AsyncMock()
                mock_read.return_value.output = "test output"
                mock_read.return_value.execution_time = 0.01

                # Execute commands concurrently
                tasks = []
                for session_id in session_ids:
                    task = session_manager.execute_command(session_id, "test command")
                    tasks.append(task)

                await asyncio.gather(*tasks)

            execution_time = time.perf_counter() - start_time

            print("Concurrent Command Execution:")
            print(f"  Commands: {len(session_ids)}")
            print(f"  Duration: {execution_time:.3f}s")
            print(f"  Rate: {len(session_ids) / execution_time:.1f} commands/sec")

            # Performance assertions
            assert execution_time < 2.0, f"Concurrent execution took {execution_time:.3f}s (>2s)"

        finally:
            await session_manager.cleanup_all()

    async def test_memory_usage_profiling(self, benchmark_timeout):
        """Test memory usage profiling."""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        session_manager = SessionManager()
        # buffers list not needed for this test

        try:
            # Create multiple sessions with large buffers
            session_count = 10
            buffer_size = 1024 * 1024  # 1MB each

            for _i in range(session_count):
                session_id = await session_manager.create_session(buffer_size=buffer_size)

                # Add test data to buffers
                session = session_manager.sessions[session_id]
                test_data = b"x" * (buffer_size // 10)  # Fill 10% of buffer
                for _j in range(10):
                    await session.output_buffer.append(test_data)

            # Measure memory after allocation
            mid_memory = process.memory_info().rss / (1024 * 1024)  # MB
            memory_increase = mid_memory - initial_memory

            print("Memory Usage Profiling:")
            print(f"  Initial memory: {initial_memory:.2f}MB")
            print(f"  After allocation: {mid_memory:.2f}MB")
            print(f"  Memory increase: {memory_increase:.2f}MB")
            print(f"  Per session: {memory_increase / session_count:.2f}MB")

            # Cleanup sessions
            await session_manager.cleanup_all()

            # Allow garbage collection
            await asyncio.sleep(0.1)

            # Measure memory after cleanup
            final_memory = process.memory_info().rss / (1024 * 1024)  # MB
            memory_leaked = final_memory - initial_memory

            print(f"  After cleanup: {final_memory:.2f}MB")
            print(f"  Memory leaked: {memory_leaked:.2f}MB")

            # Memory assertions
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

        # Fill buffer beyond capacity
        for i in range(chunks_to_overflow):
            await buffer.append(test_chunk)

            # Periodically check buffer stays within limits
            if i % 100 == 0:
                current_size = await buffer.get_size()
                assert current_size <= buffer_size * 1.1, f"Buffer size {current_size} exceeds limit"

        # Drain buffer
        chunks = await buffer.drain_all()
        end_time = time.perf_counter()

        duration = end_time - start_time
        operations_per_sec = chunks_to_overflow / duration

        print("Buffer Overflow Performance:")
        print(f"  Operations: {chunks_to_overflow}")
        print(f"  Duration: {duration:.3f}s")
        print(f"  Rate: {operations_per_sec:.0f} ops/sec")
        print(f"  Final chunks: {len(chunks)}")

        # Performance assertions
        assert operations_per_sec > 1000, f"Operation rate {operations_per_sec:.0f} ops/sec is too low"
        assert duration < 5.0, f"Overflow test took {duration:.3f}s (>5s)"

        # Verify buffer maintained size limit
        final_size = sum(len(chunk) for chunk in chunks)
        assert final_size <= buffer_size, f"Final buffer size {final_size} exceeds limit {buffer_size}"

    async def test_command_execution_latency(self, benchmark_timeout):
        """Test command execution latency."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session()

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):
                # Mock fast command execution
                mock_read.return_value = AsyncMock()
                mock_read.return_value.output = "fast command output"
                mock_read.return_value.execution_time = 0.001

                execution_times = []

                # Execute multiple commands and measure latency
                for i in range(50):
                    start_time = time.perf_counter()
                    await session_manager.execute_command(session_id, f"command {i}")
                    end_time = time.perf_counter()

                    execution_time = end_time - start_time
                    execution_times.append(execution_time)

                # Calculate statistics
                avg_time = sum(execution_times) / len(execution_times)
                p95_time = sorted(execution_times)[int(0.95 * len(execution_times))]
                max_time = max(execution_times)

                print("Command Execution Latency:")
                print(f"  Average: {avg_time * 1000:.2f}ms")
                print(f"  95th percentile: {p95_time * 1000:.2f}ms")
                print(f"  Maximum: {max_time * 1000:.2f}ms")

                # Performance assertions
                assert avg_time < 0.01, f"Average latency {avg_time * 1000:.2f}ms exceeds 10ms"
                assert p95_time < 0.02, f"95th percentile {p95_time * 1000:.2f}ms exceeds 20ms"
                assert max_time < 0.05, f"Max latency {max_time * 1000:.2f}ms exceeds 50ms"

        finally:
            await session_manager.cleanup_all()


@pytest.mark.asyncio
class TestStressTests:
    """Stress tests for interactive shell functionality."""

    async def test_long_running_session_stability(self):
        """Test long-running session stability."""
        session_manager = SessionManager()

        try:
            session_id = await session_manager.create_session()

            with (
                patch("openroad_mcp.interactive.session.InteractiveSession.send_command"),
                patch("openroad_mcp.interactive.session.InteractiveSession.read_output") as mock_read,
            ):
                mock_read.return_value = AsyncMock()
                mock_read.return_value.output = "stable output"
                mock_read.return_value.execution_time = 0.001

                # Simulate long-running session with many commands
                command_count = 1000
                batch_size = 50

                for batch in range(0, command_count, batch_size):
                    # Execute batch of commands
                    tasks = []
                    for i in range(batch, min(batch + batch_size, command_count)):
                        task = session_manager.execute_command(session_id, f"command {i}")
                        tasks.append(task)

                    await asyncio.gather(*tasks)

                    # Verify session is still alive
                    info = await session_manager.get_session_info(session_id)
                    assert info.command_count == batch + batch_size or info.command_count == command_count

                    # Small delay to prevent overwhelming
                    await asyncio.sleep(0.001)

                print(f"Long-running session executed {command_count} commands successfully")

        finally:
            await session_manager.cleanup_all()

    async def test_resource_exhaustion_handling(self):
        """Test handling of resource exhaustion scenarios."""
        session_manager = SessionManager()

        try:
            # Test maximum sessions with small buffers
            max_sessions = 100
            small_buffer_size = 1024  # 1KB

            session_ids = []

            # Create many sessions
            for i in range(max_sessions):
                try:
                    session_id = await session_manager.create_session(buffer_size=small_buffer_size)
                    session_ids.append(session_id)
                except Exception as e:
                    # Accept resource limits gracefully
                    print(f"Resource limit reached at {i} sessions: {e}")
                    break

            print(f"Created {len(session_ids)} sessions before resource exhaustion")

            # Verify sessions are manageable
            assert len(session_ids) >= 20, "Should support at least 20 concurrent sessions"

            # Test cleanup under resource pressure
            cleanup_start = time.perf_counter()
            await session_manager.cleanup_all()
            cleanup_time = time.perf_counter() - cleanup_start

            print(f"Cleanup completed in {cleanup_time:.3f}s")
            assert cleanup_time < 10.0, f"Cleanup took {cleanup_time:.3f}s (>10s)"

        finally:
            await session_manager.cleanup_all()

    async def test_large_output_handling(self):
        """Test handling of large output data."""
        session_manager = SessionManager()

        try:
            # Create session with large buffer
            large_buffer_size = 10 * 1024 * 1024  # 10MB
            session_id = await session_manager.create_session(buffer_size=large_buffer_size)

            # Simulate large output
            session = session_manager.sessions[session_id]
            large_chunk_size = 1024 * 1024  # 1MB chunks
            large_chunk = b"x" * large_chunk_size

            start_time = time.perf_counter()

            # Add large chunks to buffer
            for _i in range(5):  # 5MB total
                await session.output_buffer.append(large_chunk)

            # Read large output
            chunks = await session.output_buffer.drain_all()
            total_size = sum(len(chunk) for chunk in chunks)

            end_time = time.perf_counter()
            duration = end_time - start_time

            print("Large Output Handling:")
            print(f"  Total size: {total_size / (1024 * 1024):.2f}MB")
            print(f"  Duration: {duration:.3f}s")
            print(f"  Throughput: {(total_size / (1024 * 1024)) / duration:.2f}MB/s")

            # Performance assertions
            assert total_size > 4 * 1024 * 1024, "Should handle at least 4MB of data"
            assert duration < 2.0, f"Large output handling took {duration:.3f}s (>2s)"

        finally:
            await session_manager.cleanup_all()


if __name__ == "__main__":
    # Allow running benchmarks directly
    pytest.main([__file__, "-v", "-s"])
