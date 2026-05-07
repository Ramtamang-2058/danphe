"""
router.py — pick the cheapest model that can handle the task.

Priority:
  1. NVIDIA glm-4.7       — fast, free, native tool-call  (< 6K tokens)
  2. NVIDIA deepseek-flash — 1M ctx, free, coding          (< 60K tokens)
  3. NVIDIA nemotron-super — heavy reasoning, free          (any size)
  4. Gemini Flash          — fallback when NVIDIA unavailable
  5. devloop bridge        — last resort (no API key needed)
"""
from __future__ import annotations
from danphe import config

# Rough token estimate: 1 token ≈ 4 chars
def _estimate_tokens(messages: list[dict]) -> int:
    total = sum(len(m.get("content", "")) for m in messages)
    return total // 4


def pick(messages: list[dict]) -> tuple[str, str]:
    """
    Returns (backend, model_tier).
    backend:    "nvidia" | "gemini" | "devloop"
    model_tier: "fast" | "long" | "reasoning"  (nvidia only)
    """
    force = config.FORCE_MODEL.lower().strip()

    if force == "gemini":
        return ("gemini", "")
    if force == "devloop":
        return ("devloop", "")
    if force in ("glm", "fast"):
        return ("nvidia", "fast")
    if force in ("deepseek", "long"):
        return ("nvidia", "long")
    if force in ("nemotron", "reasoning"):
        return ("nvidia", "reasoning")

    # Auto-route: Gemini first (faster latency), NVIDIA as fallback
    tokens = _estimate_tokens(messages)
    has_nvidia = bool(config.NVIDIA_API_KEY)
    has_gemini = bool(config.GEMINI_API_KEY)

    if has_gemini:
        return ("gemini", "")

    if has_nvidia:
        if tokens < 6_000:
            return ("nvidia", "fast")       # glm-4.7: fastest
        elif tokens < 60_000:
            return ("nvidia", "long")       # deepseek-flash: big context
        else:
            return ("nvidia", "reasoning")  # nemotron: heavy lifting

    # No API keys — fall back to browser bridge
    return ("devloop", "")


def describe(backend: str, tier: str) -> str:
    """Human-readable model label for display."""
    if backend == "nvidia":
        names = {"fast": "glm-4.7", "long": "deepseek-v4-flash", "reasoning": "nemotron-super"}
        return f"NVIDIA · {names.get(tier, tier)}"
    if backend == "gemini":
        return "Gemini Flash"
    return "devloop bridge"
