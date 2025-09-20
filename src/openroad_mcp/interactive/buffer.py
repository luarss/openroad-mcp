"""Circular buffer for efficient output management with memory bounds."""

import asyncio
from collections import deque

from ..utils.logging import get_logger

logger = get_logger("circular_buffer")


class CircularBuffer:
    """Thread-safe circular buffer for output management with automatic eviction."""

    def __init__(self, max_size: int = 128 * 1024) -> None:
        """Initialize circular buffer with maximum size in bytes.

        Args:
            max_size: Maximum total size in bytes before eviction starts
        """
        self.max_size = max_size
        self.chunks: deque[bytes] = deque()
        self.total_bytes = 0
        self._lock = asyncio.Lock()
        self._data_available = asyncio.Event()

        logger.debug(f"Created CircularBuffer with max_size={max_size} bytes")

    async def append(self, data: bytes) -> None:
        """Add data to buffer, evicting oldest chunks if needed.

        Args:
            data: Bytes to add to the buffer
        """
        if not data:
            return

        async with self._lock:
            # Add new chunk
            self.chunks.append(data)
            self.total_bytes += len(data)

            # Evict oldest chunks if exceeding limit, but keep at least the newest chunk
            evicted_bytes = 0
            while self.total_bytes > self.max_size and len(self.chunks) > 1:
                old_chunk = self.chunks.popleft()
                old_size = len(old_chunk)
                self.total_bytes -= old_size
                evicted_bytes += old_size

            # Special case: if single chunk exceeds max_size and max_size > 0, keep it anyway
            # If max_size is 0, evict everything
            if self.max_size == 0 and self.chunks:
                evicted_chunk = self.chunks.popleft()
                self.total_bytes -= len(evicted_chunk)
                evicted_bytes += len(evicted_chunk)

            if evicted_bytes > 0:
                logger.debug(f"Evicted {evicted_bytes} bytes, buffer now {self.total_bytes} bytes")

            # Signal that data is available
            self._data_available.set()

    async def drain_all(self) -> list[bytes]:
        """Remove and return all buffered data.

        Returns:
            List of byte chunks that were in the buffer
        """
        async with self._lock:
            result = list(self.chunks)
            self.chunks.clear()
            self.total_bytes = 0
            self._data_available.clear()

            if result:
                total_drained = sum(len(chunk) for chunk in result)
                logger.debug(f"Drained {len(result)} chunks ({total_drained} bytes)")

            return result

    async def peek_all(self) -> list[bytes]:
        """Return all buffered data without removing it.

        Returns:
            List of byte chunks currently in the buffer
        """
        async with self._lock:
            return list(self.chunks)

    async def get_size(self) -> int:
        """Get current buffer size in bytes.

        Returns:
            Current total size of buffered data
        """
        async with self._lock:
            return self.total_bytes

    async def get_chunk_count(self) -> int:
        """Get number of chunks in buffer.

        Returns:
            Number of separate chunks stored
        """
        async with self._lock:
            return len(self.chunks)

    async def wait_for_data(self, timeout: float | None = None) -> bool:
        """Wait for new data to be available.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if data became available, False if timeout
        """
        try:
            await asyncio.wait_for(self._data_available.wait(), timeout=timeout)
        except TimeoutError:
            return False
        else:
            return True

    async def clear(self) -> None:
        """Clear all buffered data."""
        async with self._lock:
            cleared_bytes = self.total_bytes
            self.chunks.clear()
            self.total_bytes = 0
            self._data_available.clear()

            if cleared_bytes > 0:
                logger.debug(f"Cleared {cleared_bytes} bytes from buffer")

    def to_bytes(self, chunks: list[bytes]) -> bytes:
        """Convert list of chunks to single bytes object.

        Args:
            chunks: List of byte chunks to concatenate

        Returns:
            Concatenated bytes
        """
        if not chunks:
            return b""
        return b"".join(chunks)

    def to_string(self, chunks: list[bytes], encoding: str = "utf-8", errors: str = "replace") -> str:
        """Convert list of chunks to string with error handling.

        Args:
            chunks: List of byte chunks to convert
            encoding: Text encoding to use
            errors: How to handle encoding errors

        Returns:
            Decoded string
        """
        if not chunks:
            return ""

        combined = self.to_bytes(chunks)
        return combined.decode(encoding, errors=errors)

    async def get_stats(self) -> dict[str, int]:
        """Get buffer statistics.

        Returns:
            Dictionary with buffer statistics
        """
        async with self._lock:
            return {
                "total_bytes": self.total_bytes,
                "chunk_count": len(self.chunks),
                "max_size": self.max_size,
                "utilization_percent": int((self.total_bytes / self.max_size) * 100) if self.max_size > 0 else 0,
            }

    def __len__(self) -> int:
        """Get current buffer size (synchronous)."""
        return self.total_bytes

    def __bool__(self) -> bool:
        """Check if buffer has data (synchronous)."""
        return self.total_bytes > 0
