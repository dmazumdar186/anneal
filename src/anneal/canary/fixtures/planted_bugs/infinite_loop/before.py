"""Drain a queue by processing items until it is empty."""
from collections import deque
from typing import Callable


def drain_queue(queue: deque, processor: Callable[[object], bool]) -> int:
    processed = 0
    # BUG: `processor` may return False to signal a retry, but the item is never
    # re-queued and `processed` is never incremented — the loop spins forever on failure.
    while queue:
        item = queue[0]
        success = processor(item)
        if success:
            queue.popleft()
            processed += 1
        # missing: else branch — item never removed on failure → infinite loop
    return processed
