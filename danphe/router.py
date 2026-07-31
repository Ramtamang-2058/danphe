"""
router.py — pick the cheapest model that can handle the task.

Priority:
  1. Groq (Llama 3.3 70b)  — ultra-fast, tool-call           (< 12K tokens)
  2. NVIDIA glm-4.7       — fast, free, native tool-call  (< 6K tokens)
  3. NVIDIA deepseek-flash — 1M ctx, free, coding          (< 60K tokens)
  4. NVIDIA nemotron-super — heavy reasoning, free          (any size)
  5. devloop bridge        — last resort (no API key needed)
"""
from __future__ import annotations
import time
from danphe import config
from danphe.llm.retry import is_rate_limited

# Rough token estimate: 1 token ≈ 4 chars
def _estimate_tokens(messages: list[dict]) -> int:
    total = sum(len(m.get("content", "")) for m in messages)
    return total // 4


# ── Session-level circuit breaker ─────────────────────────────────────────────
# Backends that hit quota/rate limits get blocked so pick() skips them and the
# agent loop escapes to the next healthy backend instead of 429-ing forever.
_BLOCKED: dict[str, tuple[str, float]] = {}  # backend -> (reason, until_ts; 0 = permanent)


def block(backend: str, reason: str) -> None:
    """Mark a backend unavailable. Transient (per-minute) blocks expire in 90s;
    daily quota blocks are permanent for this session."""
    low = reason.lower()
    transient = "per minute" in low or "tpm" in low or "per_minute" in low or "requests per minute" in low
    until = time.time() + 90 if transient else 0.0
    _BLOCKED[backend] = (reason, until)


def is_available(backend: str) -> bool:
    """True if backend isn't blocked (or its transient block has expired)."""
    if backend not in _BLOCKED:
        return True
    reason, until = _BLOCKED[backend]
    if until and time.time() >= until:
        del _BLOCKED[backend]
        return True
    return False


def blocked() -> dict[str, str]:
    """Reason per currently-blocked backend (for display)."""
    return {b: r for b, (r, _) in _BLOCKED.items()}


# Groq on_demand tier caps input+output at ~12K TPM for llama-3.3-70b.
# Reserve budget for the system prompt + tool schemas + the output cap.
GROQ_OUTPUT_CAP = 6144
GROQ_OVERHEAD = 1800
GROQ_BUDGET = 11500


def _fits_groq(tokens: int) -> bool:
    return tokens + GROQ_OVERHEAD + GROQ_OUTPUT_CAP <= GROQ_BUDGET


def pick(messages: list[dict]) -> tuple[str, str]:
    """
    Returns (backend, model_tier).
    backend:    "groq" | "nvidia" | "devloop"
    model_tier: "fast" | "long" | "reasoning"  (nvidia only)
    """
    force = config.FORCE_MODEL.lower().strip()

    if force == "groq" and is_available("groq"):
        return ("groq", "")
    if force == "devloop":
        return ("devloop", "")
    if force in ("glm", "fast"):
        return ("nvidia", "fast")
    if force in ("deepseek", "long"):
        return ("nvidia", "long")
    if force in ("nemotron", "reasoning"):
        return ("nvidia", "reasoning")

    # Auto-route
    tokens = _estimate_tokens(messages)
    has_groq   = bool(config.GROQ_API_KEY)
    has_nvidia = bool(config.NVIDIA_API_KEY)

    # 1. Groq is the speed king for small context (input+output must fit its TPM cap)
    if has_groq and is_available("groq") and _fits_groq(tokens):
        return ("groq", "")

    # 2. NVIDIA tiers
    if has_nvidia and is_available("nvidia"):
        if tokens < 6_000:
            return ("nvidia", "fast")
        elif tokens < 60_000:
            return ("nvidia", "long")
        else:
            return ("nvidia", "reasoning")

    # No API keys — fall back to browser bridge
    return ("devloop", "")


def describe(backend: str, tier: str) -> str:
    """Human-readable model label for display."""
    if backend == "groq":
        return "Groq · Llama-3.3-70b"
    if backend == "nvidia":
        names = {"fast": "glm-5.2", "long": "deepseek-v4-flash", "reasoning": "nemotron-super"}
        return f"NVIDIA · {names.get(tier, tier)}"
    return "devloop bridge"
