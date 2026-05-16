"""Drain a queue by processing items until it is empty."""
from collections import deque
from typing import Callable


def drain_queue(queue: deque, processor: Callable[[object], bool]) -> int:
    processed = 0
    while queue:
        item = queue[0]
        success = processor(item)
        if success:
            queue.popleft()
            processed += 1
        else:
            # FIX: discard the item on failure to avoid spinning forever.
            # Callers that want retry semantics should handle retries in `processor` itself.
            queue.popleft()
    return processed
