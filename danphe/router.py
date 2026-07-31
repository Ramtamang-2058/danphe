"""
router.py — pick the cheapest model that can handle the task.

Priority:
  1. Groq (Llama 3.3 70b)  — ultra-fast, tool-call           (< 12K tokens)
  2. NVIDIA glm-4.7       — fast, free, native tool-call  (< 6K tokens)
  3. NVIDIA deepseek-flash — 1M ctx, free, coding          (< 60K tokens)
  4. NVIDIA nemotron-super — heavy reasoning, free          (any size)
  5. Gemini Flash          — fallback when NVIDIA/Groq unavailable
  6. devloop bridge        — last resort (no API key needed)
"""
from __future__ import annotations
from danphe import config

# Rough token estimate: 1 token ≈ 4 chars
def _estimate_tokens(messages: list[dict]) -> int:
    total = sum(len(m.get("content", "")) for m in messages)
    return total // 4


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
    backend:    "groq" | "nvidia" | "gemini" | "devloop"
    model_tier: "fast" | "long" | "reasoning"  (nvidia only)
    """
    force = config.FORCE_MODEL.lower().strip()

    if force == "groq":
        return ("groq", "")
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

    # Auto-route
    tokens = _estimate_tokens(messages)
    has_groq   = bool(config.GROQ_API_KEY)
    has_nvidia = bool(config.NVIDIA_API_KEY)
    has_gemini = bool(config.GEMINI_API_KEY)

    # 1. Groq is the speed king for small context (input+output must fit its TPM cap)
    if has_groq and _fits_groq(tokens):
        return ("groq", "")

    # 2. Gemini is next fastest
    if has_gemini:
        return ("gemini", "")

    # 3. NVIDIA tiers
    if has_nvidia:
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
        names = {"fast": "glm-4.7", "long": "deepseek-v4-flash", "reasoning": "nemotron-super"}
        return f"NVIDIA · {names.get(tier, tier)}"
    if backend == "gemini":
        return "Gemini Flash"
    return "devloop bridge"
