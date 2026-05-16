"""Consume all tasks from a work queue, running each through an executor."""
from collections import deque
from typing import Callable


def consume_tasks(work_queue: deque, executor: Callable[[object], bool]) -> int:
    completed = 0
    while work_queue:
        task = work_queue[0]
        done = executor(task)
        if done:
            work_queue.popleft()
            completed += 1
        # BUG: failed tasks are never removed — same infinite-loop on persistent failure
    return completed
