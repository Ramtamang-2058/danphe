"""
llm/retry.py — exponential backoff for rate-limited LLM calls.
"""
from __future__ import annotations
import random
import time

_RATE_MARKERS = (
    "429", "rate_limit", "rate limit", "resource_exhausted",
    "quota", "too many requests", "tokens per minute",
)


def is_rate_limited(exc: Exception) -> bool:
    err = str(exc).lower()
    return any(marker in err for marker in _RATE_MARKERS)


def with_backoff(fn, max_retries: int = 3, base_delay: float = 1.5):
    """Call fn(); retry on rate-limit errors with exponential backoff + jitter."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            if not is_rate_limited(e) or attempt == max_retries:
                raise
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
    raise AssertionError("unreachable")
