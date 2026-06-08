"""
llm/gemini.py — Google Gemini Flash fallback (free tier).
Migrated to google-genai SDK (google.generativeai is deprecated).
"""
from __future__ import annotations
import json
import uuid
from typing import Iterator

from danphe.config import GEMINI_API_KEY, MAX_TOKENS, DEBUG

_client = None

def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set. Add it to .env")
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _openai_tools_to_gemini(tools: list[dict]):
    """Convert OpenAI-format tool schemas to google.genai Tool list."""
    from google.genai import types
    declarations = []
    for t in tools:
        fn = t["function"]
        declarations.append(
            types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=fn.get("parameters"),
            )
        )
    return [types.Tool(function_declarations=declarations)]


def _openai_messages_to_gemini(messages: list[dict]):
    """
    Convert OpenAI-format message list to google.genai Content history + last user text.
    Returns (history: list[Content], last_user: str).
    """
    from google.genai import types

    history: list = []
    last_user = ""

    i = 0
    while i < len(messages):
        m = messages[i]
        role = m.get("role")

        if role == "user":
            last_user = m.get("content") or ""
            history.append(
                types.Content(role="user", parts=[types.Part(text=last_user)])
            )
            i += 1

        elif role == "assistant":
            tool_calls = m.get("tool_calls", [])
            if tool_calls:
                parts = []
                if m.get("content"):
                    parts.append(types.Part(text=m["content"]))
                for tc in tool_calls:
                    fn = tc["function"]
                    try:
                        args = json.loads(fn["arguments"])
                    except Exception:
                        args = {}
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                name=fn["name"], args=args
                            )
                        )
                    )
                history.append(types.Content(role="model", parts=parts))
            else:
                history.append(
                    types.Content(
                        role="model", parts=[types.Part(text=m.get("content") or "")]
                    )
                )
            i += 1

        elif role == "tool":
            tool_call_id = m.get("tool_call_id", "")
            result_content = m.get("content", "")
            # Find tool name from the preceding model message
            name = tool_call_id
            for prev in reversed(history):
                if prev.role == "model":
                    for part in prev.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            name = part.function_call.name
                    break
            history.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=name, response={"output": result_content}
                            )
                        )
                    ],
                )
            )
            i += 1

        else:
            i += 1

    # Strip the last user turn — it's sent via send_message, not history
    if history and history[-1].role == "user":
        history = history[:-1]

    return history, last_user


def stream_with_tools(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model: str = "gemini-2.0-flash",
) -> Iterator[tuple[str, object]]:
    """
    Stream from Gemini with tool calling support.
    Yields ("text", str) and ("tool_call", dict).

    Handles network interruptions gracefully.
    """
    from google.genai import types

    client = _get_client()
    gemini_tools = _openai_tools_to_gemini(tools) if tools else None
    history, last_user = _openai_messages_to_gemini(messages)

    config = types.GenerateContentConfig(
        system_instruction=system or None,
        tools=gemini_tools,
        max_output_tokens=MAX_TOKENS,
    )

    if DEBUG:
        print(f"[danphe debug] gemini model={model} tools={bool(tools)} history={len(history)}")

    chat = client.chats.create(
        model=model,
        history=history,
        config=config,
    )

    try:
        response = chat.send_message_stream(last_user or " ")
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise  # Let the caller handle rate limits
        yield ("text", f"\n[Gemini setup error: {e}]")
        return

    tool_calls: list[dict] = []

    try:
        for chunk in response:
            if not getattr(chunk, "candidates", None) or not chunk.candidates:
                continue
            candidate = chunk.candidates[0]
            if not getattr(candidate, "content", None) or not candidate.content.parts:
                continue
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fc = part.function_call
                    tool_calls.append({
                        "id": str(uuid.uuid4()),
                        "name": fc.name,
                        "args": dict(fc.args),
                    })
                elif getattr(part, "text", None):
                    yield ("text", part.text)
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            raise
        yield ("text", f"\n[Gemini stream error: {e}]")

    for tc in tool_calls:
        yield ("tool_call", tc)


def stream(
    messages: list[dict],
    system: str = "",
    model: str = "gemini-2.0-flash",
) -> Iterator[str]:
    """Plain text stream (no tools). Yields string chunks."""
    for kind, data in stream_with_tools(messages, system=system, tools=None, model=model):
        if kind == "text":
            yield data


def complete(messages: list[dict], system: str = "", model: str = "gemini-2.0-flash") -> str:
    return "".join(stream(messages, system=system, model=model))
