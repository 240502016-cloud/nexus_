from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    """Tek process içi, sabit pencereli hız sınırlayıcı.

    Bu projenin ölçeğinde (tek uvicorn worker) Redis gibi paylaşımlı bir depoya gerek yok;
    birden fazla worker/instance'a geçilirse bu bellek-içi sayaç artık yeterli olmaz.
    """

    def __init__(self, max_calls: int, window_seconds: float):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_calls:
            return False
        hits.append(now)
        return True
