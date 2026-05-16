"""Concurrently track the number of active sessions across threads."""
import threading


class SessionTracker:
    def __init__(self) -> None:
        self._active = 0

    def register(self) -> None:
        # BUG: same race — unprotected read-modify-write
        self._active += 1

    def count(self) -> int:
        return self._active


def spawn_sessions(n: int) -> SessionTracker:
    tracker = SessionTracker()
    threads = [threading.Thread(target=tracker.register) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return tracker
