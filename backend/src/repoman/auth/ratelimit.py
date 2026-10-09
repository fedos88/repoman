"""In-process limiter for failed login attempts (single-process deployment, see design §2)."""

import time
from collections import deque


class LoginRateLimiter:
    def __init__(
        self, max_failures: int = 5, window_seconds: float = 900, max_keys: int = 10_000
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        # Expired entries are pruned when the number of tracked keys exceeds this value.
        self.max_keys = max_keys
        self._failures: dict[tuple[str, str], deque[float]] = {}

    def _recent(self, key: tuple[str, str], now: float) -> deque[float]:
        failures = self._failures.get(key)
        if failures is None:
            return deque()
        while failures and now - failures[0] > self.window_seconds:
            failures.popleft()
        if not failures:
            del self._failures[key]
        return failures

    def is_blocked(self, username: str, ip: str) -> bool:
        return len(self._recent((username, ip), time.monotonic())) >= self.max_failures

    def record_failure(self, username: str, ip: str) -> None:
        now = time.monotonic()
        if len(self._failures) > self.max_keys:
            for stale in list(self._failures):
                self._recent(stale, now)
        key = (username, ip)
        failures = self._recent(key, now)
        failures.append(now)
        self._failures[key] = failures

    def reset(self, username: str, ip: str) -> None:
        self._failures.pop((username, ip), None)
