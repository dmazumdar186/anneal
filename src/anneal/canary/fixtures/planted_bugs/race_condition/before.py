"""Thread-safe counter incremented by multiple worker threads."""
import threading


class RequestCounter:
    def __init__(self) -> None:
        self._count = 0

    def increment(self) -> None:
        # BUG: read-modify-write is not atomic; concurrent calls lose increments.
        self._count += 1

    def value(self) -> int:
        return self._count


def run_workers(n: int) -> RequestCounter:
    counter = RequestCounter()
    threads = [threading.Thread(target=counter.increment) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter
