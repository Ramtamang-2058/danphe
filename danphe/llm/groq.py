"""
llm/groq.py — Groq Cloud inference (Llama 3.3 70B / Mixtral).
Optimized for high-speed agentic tasks.
"""
from __future__ import annotations
import json
import uuid
from typing import Iterator

from danphe.config import GROQ_API_KEY, MAX_TOKENS, DEBUG

_client = None

def _get_client():
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set. Add it to .env")
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _build_messages(messages: list[dict], system: str) -> list[dict]:
    """Prepend system message if not already present."""
    if not system:
        return messages
    if any(m.get("role") == "system" for m in messages):
        return messages
    return [{"role": "system", "content": system}] + messages


def stream_with_tools(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model: str = "llama-3.3-70b-versatile",
) -> Iterator[tuple[str, object]]:
    """
    Stream from Groq with tool calling support.
    Yields ("text", str) and ("tool_call", dict).
    """
    client = _get_client()
    all_messages = _build_messages(messages, system)

    kwargs: dict = dict(
        model=model,
        messages=all_messages,
        temperature=1,
        max_tokens=MAX_TOKENS,
        stream=True,
    )
    if tools:
        # Convert tool schemas to the format Groq expects (OpenAI-like)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    if DEBUG:
        print(f"[danphe debug] groq model={model} tools={bool(tools)}")

    try:
        completion = client.chat.completions.create(**kwargs)
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            raise RuntimeError(f"RATE_LIMITED: {e}")
        yield ("text", f"\n[Groq error: {e}]")
        return

    accumulated: dict[int, dict] = {}

    try:
        for chunk in completion:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            
            # Text content
            if hasattr(delta, "content") and delta.content:
                yield ("text", delta.content)

            # Tool call deltas
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in accumulated:
                        accumulated[idx] = {"id": "", "name": "", "args": ""}
                    if hasattr(tc, "id") and tc.id:
                        accumulated[idx]["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn:
                        if hasattr(fn, "name") and fn.name:
                            accumulated[idx]["name"] = fn.name
                        if hasattr(fn, "arguments") and fn.arguments:
                            accumulated[idx]["args"] += fn.arguments
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            raise RuntimeError(f"RATE_LIMITED: {e}")
        yield ("text", f"\n[Groq streaming error: {e}]")

    # Emit completed tool calls
    for idx in sorted(accumulated.keys()):
        tc = accumulated[idx]
        try:
            args = json.loads(tc["args"]) if tc["args"].strip() else {}
        except json.JSONDecodeError:
            args = {"_raw": tc["args"]}
        yield ("tool_call", {"id": tc["id"] or str(uuid.uuid4()), "name": tc["name"], "args": args})


def stream(
    messages: list[dict],
    system: str = "",
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Plain text stream (no tools). Yields string chunks."""
    client = _get_client()
    all_messages = _build_messages(messages, system)
    
    kwargs = dict(
        model=model,
        messages=all_messages,
        temperature=1,
        max_tokens=max_tokens or MAX_TOKENS,
        stream=True,
    )
    
    try:
        completion = client.chat.completions.create(**kwargs)
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            raise RuntimeError(f"RATE_LIMITED: {e}")
        yield f"\n[Groq error: {e}]"


def complete(
    messages: list[dict], 
    system: str = "", 
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int | None = None,
) -> str:
    """Full text completion."""
    return "".join(stream(messages, system=system, model=model, max_tokens=max_tokens))
