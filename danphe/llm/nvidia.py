"""
llm/nvidia.py — NVIDIA NIM streaming client (OpenAI-compatible endpoint).
Model IDs taken directly from NVIDIA's sample code at build.nvidia.com.
"""
from __future__ import annotations
import json
from typing import Iterator

from openai import OpenAI

from danphe.config import NVIDIA_API_KEY, MAX_TOKENS, DEBUG
from danphe.llm.retry import with_backoff

MODELS = {
    "fast":      "z-ai/glm-5.2",                      # GLM-5.2: agentic, tool-calling, thinking
    "long":      "deepseek-ai/deepseek-v4-flash",      # DeepSeek V4 Flash: long ctx, coding
    "reasoning": "nvidia/nemotron-3-super-120b-a12b",  # Nemotron: heavy reasoning
}

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY not set — add it to .env")
        _client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_API_KEY,
        )
    return _client


def _build_messages(messages: list[dict], system: str) -> list[dict]:
    """Prepend system message if not already present."""
    if not system:
        return messages
    if any(m.get("role") == "system" for m in messages):
        return messages
    return [{"role": "system", "content": system}] + messages


def _thinking_body(tier: str) -> dict | None:
    """Return extra_body for thinking mode, or None."""
    if tier in ("fast", "reasoning"):
        return {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        }
    return None


# ── Streaming text (no tool calling) ──────────────────────────────────────────

def stream(
    messages: list[dict],
    model_tier: str = "fast",
    system: str = "",
) -> Iterator[str]:
    """
    Stream text tokens from NVIDIA NIM.
    Yields string chunks (reasoning tokens skipped unless DEBUG=1).

    Handles network interruptions gracefully.
    """
    client = _get_client()
    model = MODELS.get(model_tier, MODELS["fast"])
    all_messages = _build_messages(messages, system)

    if DEBUG:
        print(f"[danphe debug] model={model} msgs={len(all_messages)}")

    kwargs: dict = dict(
        model=model,
        messages=all_messages,
        temperature=0.7,
        top_p=1,
        max_tokens=MAX_TOKENS,
        stream=True,
    )
    thinking_body = _thinking_body(model_tier)
    if thinking_body:
        kwargs["extra_body"] = thinking_body

    completion = with_backoff(lambda: client.chat.completions.create(**kwargs))

    try:
        for chunk in completion:
            if not getattr(chunk, "choices", None) or not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and DEBUG:
                print(f"\033[90m{reasoning}\033[0m", end="", flush=True)

            if getattr(delta, "content", None):
                yield delta.content
    except (IOError, RuntimeError) as e:
        # Network interruption
        err_msg = str(e)
        if "peer closed" in err_msg.lower() or "incomplete" in err_msg.lower():
            yield f"\n[Stream interrupted: {err_msg}]"
        else:
            yield f"\n[Stream error: {err_msg}]"
    except Exception as e:
        yield f"\n[Unexpected streaming error: {e}]"


def complete(
    messages: list[dict],
    model_tier: str = "fast",
    system: str = "",
) -> str:
    """Non-streaming — returns full response string."""
    return "".join(stream(messages, model_tier=model_tier, system=system))


# ── Streaming with tool calling ────────────────────────────────────────────────

def stream_with_tools(
    messages: list[dict],
    model_tier: str = "fast",
    system: str = "",
    tools: list[dict] | None = None,
) -> Iterator[tuple[str, object]]:
    """
    Stream response with optional tool calling.

    Yields:
      ("text",      str)               — text chunk to display live
      ("tool_call", dict)              — completed tool call after stream ends
          dict keys: id, name, args (parsed dict)

    Falls back to plain streaming (no tools) if the API rejects tool params.

    Handles network interruptions gracefully with error reporting.
    """
    client = _get_client()
    model = MODELS.get(model_tier, MODELS["fast"])
    all_messages = _build_messages(messages, system)

    if DEBUG:
        print(f"[danphe debug] model={model} tools={bool(tools)} msgs={len(all_messages)}")

    kwargs: dict = dict(
        model=model,
        messages=all_messages,
        temperature=0.3,
        top_p=1,
        max_tokens=MAX_TOKENS,
        stream=True,
    )

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    else:
        thinking_body = _thinking_body(model_tier)
        if thinking_body:
            kwargs["extra_body"] = thinking_body

    # Try with tools; on failure fall back to plain stream
    try:
        completion = with_backoff(lambda: client.chat.completions.create(**kwargs))
    except Exception as e:
        err = str(e).lower()
        if tools and ("tool" in err or "function" in err or "unsupported" in err):
            # Model doesn't support tool calling — strip tools and retry
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)
            thinking_body = _thinking_body(model_tier)
            if thinking_body:
                kwargs["extra_body"] = thinking_body
            completion = with_backoff(lambda: client.chat.completions.create(**kwargs))
        else:
            raise

    accumulated: dict[int, dict] = {}

    try:
        for chunk in completion:
            if not getattr(chunk, "choices", None) or not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue

            # Reasoning tokens (thinking mode)
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and DEBUG:
                print(f"\033[90m{reasoning}\033[0m", end="", flush=True)

            # Text content — yield immediately for live streaming
            if getattr(delta, "content", None):
                yield ("text", delta.content)

            # Tool call deltas — accumulate across chunks
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in accumulated:
                        accumulated[idx] = {"id": "", "name": "", "args": ""}
                    if getattr(tc, "id", None):
                        accumulated[idx]["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn:
                        if getattr(fn, "name", None):
                            accumulated[idx]["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            accumulated[idx]["args"] += fn.arguments
    except (IOError, RuntimeError) as e:
        # Network interruption — yield error and any accumulated data
        err_msg = str(e)
        if "peer closed" in err_msg.lower() or "incomplete" in err_msg.lower():
            yield ("text", f"\n[Stream interrupted: {err_msg}. Use tools if needed, or retry.]")
        else:
            yield ("text", f"\n[Stream error: {err_msg}]")
        # Continue to emit any accumulated tool calls we have so far
    except Exception as e:
        # Unexpected error — report and continue
        yield ("text", f"\n[Unexpected error during streaming: {e}]")

    # Emit completed tool calls after the stream finishes (even if interrupted)
    for idx in sorted(accumulated.keys()):
        tc = accumulated[idx]
        try:
            args = json.loads(tc["args"]) if tc["args"].strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": tc["args"]}
        yield ("tool_call", {"id": tc["id"], "name": tc["name"], "args": args or {}})
