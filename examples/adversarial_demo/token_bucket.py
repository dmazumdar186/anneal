"""
token_bucket.py — a rate-limiter using the token-bucket algorithm.

This module *looks* production-ready: it has type hints, docstrings,
and a passing test suite.  Two subtle vulnerabilities remain hidden.

Run `anneal adversarial --tier cheap HEAD~1` to watch Red find them and
Blue patch them.
"""

from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """Thread-safe token-bucket rate limiter.

    Tokens replenish at *rate* tokens per second up to *capacity*.
    Callers consume tokens with :meth:`consume`.  Returns True when
    the request is allowed, False when the bucket is empty.

    Args:
        capacity: Maximum number of tokens (burst ceiling).
        rate: Refill rate in tokens per second.
    """

    def __init__(self, capacity: float, rate: float) -> None:
        # VULNERABILITY-1 (missing input validation — TOCTOU-adjacent):
        # capacity and rate are accepted without a positivity check.
        # A capacity=0 or rate=0 produces a degenerate bucket that
        # allows every request (tokens always >= 0 after refill) or
        # permanently blocks (tokens never refill).  Callers who
        # accidentally pass 0 get silent, unexpected behaviour.
        self.capacity = capacity
        self.rate = rate
        self._tokens = capacity          # start full
        self._last_refill = time.monotonic()
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Add tokens proportional to elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.capacity,
            self._tokens + elapsed * self.rate,
        )
        self._last_refill = now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume *tokens* from the bucket.

        Returns True if the request is allowed, False if the bucket
        does not have enough tokens.

        VULNERABILITY-2 (race condition / check-then-act):
        _refill() and the token check/decrement are NOT inside the same
        lock acquisition.  In CPython the GIL reduces the risk, but the
        check-then-act gap is real: two threads can both pass the
        `self._tokens >= tokens` guard before either decrements, causing
        the bucket to go negative — i.e., more requests are allowed than
        the rate limit permits.
        """
        with self._lock:
            self._refill()

        # BUG: lock released here — another thread can sneak in
        if self._tokens >= tokens:
            self._tokens -= tokens      # non-atomic with the check above
            return True
        return False

    def available(self) -> float:
        """Return the current token count (snapshot, not guaranteed fresh)."""
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        """Refill the bucket to capacity (e.g. for testing)."""
        with self._lock:
            self._tokens = self.capacity
            self._last_refill = time.monotonic()
