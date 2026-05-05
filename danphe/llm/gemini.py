"""
llm/gemini.py — Google Gemini Flash fallback (free tier).
"""
from __future__ import annotations
import json
import uuid
from typing import Iterator
from danphe.config import GEMINI_API_KEY, MAX_TOKENS, DEBUG

_genai = None

def _get_genai():
    global _genai
    if _genai is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set. Add it to .env")
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _genai = genai
    return _genai


def _openai_tools_to_gemini(tools: list[dict]):
    """Convert OpenAI-format tool schemas to Gemini FunctionDeclaration list."""
    genai = _get_genai()
    declarations = []
    for t in tools:
        fn = t["function"]
        params = fn.get("parameters")
        declarations.append(
            genai.types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=params,
            )
        )
    return [genai.types.Tool(function_declarations=declarations)]


def _openai_messages_to_gemini(messages: list[dict]) -> tuple[list[dict], str]:
    """
    Convert OpenAI-format message list to Gemini history + last user content.
    Handles tool call / tool result pairs → FunctionCall / FunctionResponse parts.
    Returns (history_for_start_chat, last_user_message_content).
    """
    history: list[dict] = []
    last_user = ""

    i = 0
    while i < len(messages):
        m = messages[i]
        role = m.get("role")

        if role == "user":
            last_user = m.get("content") or ""
            history.append({"role": "user", "parts": [last_user]})
            i += 1

        elif role == "assistant":
            tool_calls = m.get("tool_calls", [])
            if tool_calls:
                # Build model message with FunctionCall parts
                parts = []
                if m.get("content"):
                    parts.append(m["content"])
                for tc in tool_calls:
                    fn = tc["function"]
                    try:
                        args = json.loads(fn["arguments"])
                    except Exception:
                        args = {}
                    parts.append({"function_call": {"name": fn["name"], "args": args}})
                history.append({"role": "model", "parts": parts})
            else:
                content = m.get("content") or ""
                history.append({"role": "model", "parts": [content]})
            i += 1

        elif role == "tool":
            # Collect consecutive tool results and pair with the preceding assistant message
            tool_call_id = m.get("tool_call_id", "")
            result_content = m.get("content", "")
            # Find the tool name from the previous assistant message's tool_calls
            name = tool_call_id  # fallback
            for prev in reversed(history):
                if prev.get("role") == "model":
                    for part in prev.get("parts", []):
                        if isinstance(part, dict) and "function_call" in part:
                            name = part["function_call"]["name"]
                    break
            history.append({
                "role": "user",
                "parts": [{"function_response": {"name": name, "response": {"output": result_content}}}],
            })
            i += 1

        else:
            i += 1

    # The last history entry should be the final user message;
    # remove it since we pass it via send_message
    if history and history[-1].get("role") == "user":
        history = history[:-1]

    return history, last_user


def stream_with_tools(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
) -> Iterator[tuple[str, object]]:
    """
    Stream from Gemini with tool calling support.
    Yields ("text", str) and ("tool_call", dict) — same contract as nvidia.stream_with_tools.
    """
    genai = _get_genai()

    gemini_tools = _openai_tools_to_gemini(tools) if tools else None
    history, last_user = _openai_messages_to_gemini(messages)

    model = genai.GenerativeModel(
        model_name="gemini-3-flash-preview",
        system_instruction=system or "",
        tools=gemini_tools,
    )

    if DEBUG:
        print(f"[danphe debug] gemini tools={bool(tools)} history={len(history)}")

    chat = model.start_chat(history=history)
    response = chat.send_message(last_user or "", stream=True)

    tool_calls: list[dict] = []

    for chunk in response:
        # Text parts
        try:
            if chunk.text:
                yield ("text", chunk.text)
                continue
        except ValueError:
            pass

        # Function call parts (chunk.text raises ValueError when part is a function_call)
        try:
            for part in chunk.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fc = part.function_call
                    tool_calls.append({
                        "id": str(uuid.uuid4()),
                        "name": fc.name,
                        "args": dict(fc.args),
                    })
                elif getattr(part, "text", None):
                    yield ("text", part.text)
        except Exception:
            pass

    for tc in tool_calls:
        yield ("tool_call", tc)


def stream(
    messages: list[dict],
    system: str = "",
) -> Iterator[str]:
    """Plain text stream (no tools). Yields string chunks."""
    for kind, data in stream_with_tools(messages, system=system, tools=None):
        if kind == "text":
            yield data


def complete(messages: list[dict], system: str = "") -> str:
    return "".join(stream(messages, system=system))
