"""Property-based tests (hypothesis) for pure invariants.

These assert behavior across a wide input space rather than single examples:
RRF is a permutation, scrypt round-trips, the token bucket respects capacity,
and token estimation is monotonic and positive.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from codeatlas.agent_context import estimate_tokens
from codeatlas.hosted import _hash_token, _verify_token_hash
from codeatlas.rate_limit import TokenBucketRateLimiter
from codeatlas.search.hybrid import _reciprocal_rank_fusion

_ids = st.text(st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=6)


@given(st.lists(st.lists(_ids, max_size=8), max_size=4))
def test_rrf_is_a_permutation_of_the_union(ranked_lists: list[list[str]]) -> None:
    # Dedup each list (RRF treats repeated ids within a list by last-seen rank).
    union = {item for lst in ranked_lists for item in lst}
    merged = _reciprocal_rank_fusion(ranked_lists)
    assert set(merged) == union
    assert len(merged) == len(union)  # no duplicates


@given(st.lists(_ids, min_size=1, max_size=8, unique=True))
def test_rrf_unanimous_winner_ranks_first(items: list[str]) -> None:
    # If one id is rank-0 in every list, RRF must place it first.
    winner = items[0]
    lists = [[winner, *items[1:]], [winner, *list(reversed(items[1:]))]]
    assert _reciprocal_rank_fusion(lists)[0] == winner


@settings(deadline=None, max_examples=25)  # scrypt is intentionally slow (memory-hard)
@given(st.text(min_size=0, max_size=200))
def test_scrypt_roundtrips(token: str) -> None:
    encoded = _hash_token(token)
    assert _verify_token_hash(token, encoded)
    assert not _verify_token_hash(token + "x", encoded)


@given(st.integers(min_value=1, max_value=50))
def test_token_bucket_respects_capacity(capacity: int) -> None:
    limiter = TokenBucketRateLimiter(capacity=capacity, refill_per_second=0)
    allowed = [limiter.allow("k", now=0) for _ in range(capacity + 3)]
    assert allowed[:capacity] == [True] * capacity
    assert allowed[capacity:] == [False, False, False]


@given(st.text(min_size=0, max_size=500))
def test_estimate_tokens_positive(text: str) -> None:
    assert estimate_tokens(text) >= 1


@given(st.text(max_size=200), st.text(max_size=200))
def test_estimate_tokens_monotonic(a: str, b: str) -> None:
    if len(a) <= len(b):
        assert estimate_tokens(a) <= estimate_tokens(b)
