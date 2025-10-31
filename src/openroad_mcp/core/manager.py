"""OpenROAD process manager."""

from ..interactive.session_manager import InteractiveSessionManager
from ..utils.logging import get_logger


class OpenROADManager:
    """Singleton class to manage OpenROAD subprocess lifecycle."""

    _instance: "OpenROADManager | None" = None

    @staticmethod
    def safe_decode(data: bytes, encoding: str = "utf-8", errors: str = "replace") -> str:
        """Safely decode bytes to string with error handling for unicode issues."""
        return data.decode(encoding, errors=errors)

    def __new__(cls) -> "OpenROADManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.initialized = True
            self.logger = get_logger("manager")

            # Interactive session management (lazy initialization)
            self._interactive_manager: InteractiveSessionManager | None = None

    @property
    def interactive_manager(self) -> InteractiveSessionManager:
        """Get or create interactive session manager."""
        if self._interactive_manager is None:
            self._interactive_manager = InteractiveSessionManager()
            self.logger.info("Initialized interactive session manager")
        return self._interactive_manager

    async def cleanup_all(self) -> None:
        """Clean up interactive sessions."""
        self.logger.info("Starting OpenROAD cleanup")

        if self._interactive_manager is not None:
            try:
                await self._interactive_manager.cleanup()
                self.logger.info("Interactive sessions cleaned up")
            except Exception:
                self.logger.exception("Error cleaning up interactive sessions")

        self.logger.info("OpenROAD cleanup completed")
