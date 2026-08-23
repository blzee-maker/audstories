from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, status

from .auth import require_user


class SlidingWindowLimiter:
    """Per-key sliding-window rate limiter.

    Tracks call timestamps per key (here, per user id) and rejects a call
    once ``max_calls`` have occurred within the trailing ``window_seconds``.
    Thread-safe: a single lock guards the timestamp deques, so it is safe
    to share one instance across FastAPI request threads.

    In-process only — state is not shared across multiple worker processes.
    That matches the current single-instance deployment; move to a shared
    store (Redis) if you scale horizontally.
    """

    def __init__(self, *, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_calls:
                retry_after = max(1, int(hits[0] + self.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)


# Pipeline triggers (stage1/stage2/credits): heavy subprocess work.
pipeline_limiter = SlidingWindowLimiter(max_calls=10, window_seconds=60)
# TTS generation: directly burns paid Gemini quota — tighter budget.
tts_limiter = SlidingWindowLimiter(max_calls=6, window_seconds=60)


def rate_limited(limiter: SlidingWindowLimiter):
    """Build a dependency that enforces *limiter* per user, returning user_id.

    Use in place of ``Depends(require_user)``: it authenticates first, then
    applies the limit, and yields the same ``user_id`` the endpoints expect.
    """

    def dependency(user_id: str = Depends(require_user)) -> str:
        limiter.check(user_id)
        return user_id

    return dependency
