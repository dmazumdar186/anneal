"""HTTP retry helper with exponential backoff."""
import time


def retry_with_backoff(fn, max_attempts: int = 3, base_delay: float = 1.0):
    # try up to max_attempts times
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception:
            if attempt == max_attempts - 1:
                raise
            # wait before next retry
            time.sleep(base_delay * (2 ** attempt))
