import threading
import time

class SpacedLimiter:
    """Serialize calls and enforce a minimum interval between starts."""
    def __init__(self, min_interval_s: float = 5.0):
        self.min_interval = float(min_interval_s)
        self._lock = threading.Lock()
        self._last_start = 0.0  # monotonic seconds

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_start)
            if wait > 0:
                time.sleep(wait)
            self._last_start = time.monotonic()
