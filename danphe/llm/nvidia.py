"""
llm/nvidia.py — NVIDIA NIM streaming client (OpenAI-compatible endpoint).
Model IDs taken directly from NVIDIA's sample code at build.nvidia.com.
"""
from __future__ import annotations
from typing import Iterator
from openai import OpenAI
from danphe.config import NVIDIA_API_KEY, MAX_TOKENS, DEBUG

# Exact model IDs from NVIDIA's own sample snippets
MODELS = {
    "fast":      "z-ai/glm-5.1",                        # GLM-5.1, agentic, tool-calling, thinking
    "long":      "deepseek-ai/deepseek-v3-0324",         # DeepSeek V3, long context, coding
    "reasoning": "nvidia/nemotron-3-super-120b-a12b",    # Nemotron, heavy reasoning
}

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY not set. Add it to .env")
        _client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_API_KEY,
        )
    return _client


def stream(
    messages: list[dict],
    model_tier: str = "fast",
    system: str = "",
) -> Iterator[str]:
    """
    Stream text tokens from NVIDIA NIM.
    Yields string chunks as they arrive (reasoning tokens skipped).
    model_tier: "fast" | "long" | "reasoning"
    """
    client = _get_client()
    model  = MODELS.get(model_tier, MODELS["fast"])

    # Build message list — never duplicate system role
    all_messages: list[dict] = []
    has_system = any(m.get("role") == "system" for m in messages)
    if system and not has_system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    if DEBUG:
        print(f"[danphe debug] model={model} msgs={len(all_messages)}")

    # GLM-5.1 and nemotron support thinking mode
    enable_thinking = model_tier in ("fast", "reasoning")
    extra_body = {
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
            "clear_thinking": False,
        }
    }

    completion = client.chat.completions.create(
        model=model,
        messages=all_messages,
        temperature=1,
        top_p=1,
        max_tokens=MAX_TOKENS,
        stream=True,
        extra_body=extra_body,
    )

    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue
        if not chunk.choices or getattr(chunk.choices[0], "delta", None) is None:
            continue
        delta = chunk.choices[0].delta

        # Show reasoning in dim gray if DEBUG=1, otherwise skip silently
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning and DEBUG:
            print(f"\033[90m{reasoning}\033[0m", end="", flush=True)

        if getattr(delta, "content", None):
            yield delta.content


def complete(
    messages: list[dict],
    model_tier: str = "fast",
    system: str = "",
) -> str:
    """Non-streaming version. Returns full response string."""
    return "".join(stream(messages, model_tier=model_tier, system=system))