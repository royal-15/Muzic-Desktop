"""Thread-safe process-wide cooldown for YouTube rate limits."""
import threading
import time
import random
from typing import Callable


class RateLimitCoordinator:
    """Hold download workers while any task is backing off from HTTP 429."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._blocked_until = 0.0
        self._next_request_at = 0.0

    def defer(self, seconds: float) -> float:
        """Extend the shared cooldown and return its remaining duration."""
        with self._condition:
            self._blocked_until = max(
                self._blocked_until,
                time.monotonic() + max(0.0, seconds),
            )
            self._condition.notify_all()
            return max(0.0, self._blocked_until - time.monotonic())

    def remaining(self) -> float:
        """Return the current shared cooldown duration in seconds."""
        with self._condition:
            return max(0.0, self._blocked_until - time.monotonic())

    def wait(self, is_cancelled: Callable[[], bool]) -> bool:
        """Wait for and reserve a spaced request slot; return True if cancelled."""
        with self._condition:
            while True:
                if is_cancelled():
                    return True
                now = time.monotonic()
                remaining = max(self._blocked_until, self._next_request_at) - now
                if remaining <= 0:
                    # Keep workers from all resuming at once after a shared
                    # cooldown or queueing a burst during normal operation.
                    self._next_request_at = now + 2.0 + random.uniform(0.0, 1.5)
                    return False
                self._condition.wait(timeout=min(remaining, 0.2))
