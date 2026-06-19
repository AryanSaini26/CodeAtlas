"""In-memory token-bucket rate limiting for internet-facing hosted endpoints.

The webhook and remote-context endpoints are about to be public; an unrated
endpoint that clones repos or serves context is a real abuse vector. This is a
per-process limiter (one FastAPI deployment at MVP scale), keyed per
installation or per token+repo — not a distributed limiter, which would need
Redis and isn't warranted yet.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucketRateLimiter:
    """Classic token bucket: ``capacity`` burst, refilled at ``refill_per_second``."""

    def __init__(self, *, capacity: float, refill_per_second: float) -> None:
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, *, cost: float = 1.0, now: float | None = None) -> bool:
        """Consume ``cost`` tokens for ``key``; return False if the bucket is empty."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated=moment)
                self._buckets[key] = bucket
            elapsed = max(0.0, moment - bucket.updated)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated = moment
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            return False

    def retry_after_seconds(self, cost: float = 1.0) -> int:
        """Whole seconds a caller should wait before one token is available."""
        if self.refill_per_second <= 0:
            return 1
        return max(1, int(cost / self.refill_per_second))


def _limiter_from_env(
    prefix: str, *, default_capacity: float, default_refill: float
) -> TokenBucketRateLimiter:
    capacity = float(os.environ.get(f"{prefix}_CAPACITY", default_capacity))
    refill = float(os.environ.get(f"{prefix}_REFILL", default_refill))
    return TokenBucketRateLimiter(capacity=capacity, refill_per_second=refill)


def webhook_rate_limiter() -> TokenBucketRateLimiter:
    """Per-installation webhook limiter (default 60 burst, ~60/min sustained)."""
    return _limiter_from_env("STRATUM_WEBHOOK_RATE", default_capacity=60, default_refill=1.0)


def context_rate_limiter() -> TokenBucketRateLimiter:
    """Per token+repo limiter for remote MCP / context (default 120 burst, ~2/s)."""
    return _limiter_from_env("STRATUM_MCP_RATE", default_capacity=120, default_refill=2.0)
