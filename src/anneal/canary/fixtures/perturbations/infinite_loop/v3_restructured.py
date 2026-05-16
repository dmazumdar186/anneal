"""Drain a queue by processing items until it is empty."""
from collections import deque
from typing import Callable


def _process_item(
    queue: deque,
    item: object,
    processor: Callable[[object], bool],
    counter: list[int],
) -> None:
    success = processor(item)
    if success:
        queue.popleft()
        counter[0] += 1
    # BUG: no removal on failure — infinite loop if processor always returns False


def drain_queue(queue: deque, processor: Callable[[object], bool]) -> int:
    counter = [0]
    while queue:
        _process_item(queue, queue[0], processor, counter)
    return counter[0]
