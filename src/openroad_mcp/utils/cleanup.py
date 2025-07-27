"""Cleanup utilities for graceful shutdown."""

import asyncio
import atexit
import logging
import signal
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class CleanupManager:
    """Manages graceful shutdown and cleanup operations."""

    def __init__(self) -> None:
        self._shutdown_initiated = False
        self._cleanup_handlers: list[Callable[[], None]] = []
        self._async_cleanup_handlers: list[Callable[[], Any]] = []

    def register_cleanup_handler(self, handler: Callable[[], None]) -> None:
        """Register a synchronous cleanup handler."""
        self._cleanup_handlers.append(handler)

    def register_async_cleanup_handler(self, handler: Callable[[], Any]) -> None:
        """Register an asynchronous cleanup handler."""
        self._async_cleanup_handlers.append(handler)

    def signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        if self._shutdown_initiated:
            return

        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal, initiating shutdown...")

        # Create a new event loop if none exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Schedule the shutdown
        if loop.is_running():
            loop.create_task(self.async_cleanup())
        else:
            loop.run_until_complete(self.async_cleanup())

    def sync_cleanup(self) -> None:
        """Synchronous cleanup for atexit handler."""
        if self._shutdown_initiated:
            return

        logger.info("Executing atexit cleanup...")
        self._shutdown_initiated = True

        # Run sync handlers
        for handler in self._cleanup_handlers:
            try:
                handler()
            except Exception as e:
                logger.error(f"Error in sync cleanup handler: {e}")

        # Run async handlers
        if self._async_cleanup_handlers:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._run_async_handlers())
                loop.close()
            except Exception as e:
                logger.error(f"Error in async cleanup: {e}")

    async def async_cleanup(self) -> None:
        """Asynchronous cleanup."""
        if self._shutdown_initiated:
            return

        self._shutdown_initiated = True
        logger.info("Initiating graceful shutdown...")

        # Run sync handlers
        for handler in self._cleanup_handlers:
            try:
                handler()
            except Exception as e:
                logger.error(f"Error in sync cleanup handler: {e}")

        # Run async handlers
        await self._run_async_handlers()

    async def _run_async_handlers(self) -> None:
        """Run all async cleanup handlers."""
        for handler in self._async_cleanup_handlers:
            try:
                result = handler()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error in async cleanup handler: {e}")

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        atexit.register(self.sync_cleanup)


# Global cleanup manager instance
cleanup_manager = CleanupManager()
