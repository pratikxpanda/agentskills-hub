"""In-process rate limiting for failed authentication.

Lives in core because both edges authenticate. A second copy in the gateway would be a security
control that drifts, and the first symptom of the drift would be the edge that forgot to throttle.

Deliberately per-process: v0.1 runs a single instance, and a shared counter is a v0.4 concern that
arrives with horizontal scaling. Recording that here is cheaper than discovering it in production.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class FixedWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] > self._window:
            hits.popleft()
        return hits

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self._limit

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now).append(now)

    def clear(self, key: str) -> None:
        self._hits.pop(key, None)


__all__ = ["FixedWindowLimiter"]
