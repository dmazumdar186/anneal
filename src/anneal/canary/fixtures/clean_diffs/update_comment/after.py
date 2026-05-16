"""HTTP retry helper with exponential backoff."""
import time


def retry_with_backoff(fn, max_attempts: int = 3, base_delay: float = 1.0):
    # Retry the callable up to max_attempts times, doubling the delay each time.
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception:
            if attempt == max_attempts - 1:
                raise
            # Exponential backoff: base_delay * 2^attempt seconds between retries.
            time.sleep(base_delay * (2 ** attempt))
