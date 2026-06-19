"""Tests for the token-bucket rate limiter."""

from __future__ import annotations

from codeatlas.rate_limit import TokenBucketRateLimiter


def test_token_bucket_allows_burst_then_blocks() -> None:
    limiter = TokenBucketRateLimiter(capacity=3, refill_per_second=0)
    assert [limiter.allow("k", now=0) for _ in range(4)] == [True, True, True, False]
    # A different key has its own independent bucket.
    assert limiter.allow("other", now=0) is True


def test_token_bucket_refills_over_time() -> None:
    limiter = TokenBucketRateLimiter(capacity=1, refill_per_second=1)
    assert limiter.allow("k", now=0) is True
    assert limiter.allow("k", now=0) is False
    # One second later, one token has refilled.
    assert limiter.allow("k", now=1) is True


def test_retry_after_seconds() -> None:
    assert TokenBucketRateLimiter(capacity=1, refill_per_second=2).retry_after_seconds() == 1
    assert TokenBucketRateLimiter(capacity=1, refill_per_second=0).retry_after_seconds() == 1
    assert TokenBucketRateLimiter(capacity=1, refill_per_second=0.25).retry_after_seconds() == 4
