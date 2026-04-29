"""
llm/gemini.py — Google Gemini Flash fallback (free tier).
"""
from __future__ import annotations
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


def stream(
    messages: list[dict],
    system: str = "",
) -> Iterator[str]:
    """Stream from Gemini Flash. Yields string chunks."""
    genai = _get_genai()

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system or None,
    )

    # Convert OpenAI message format → Gemini format
    history = []
    last_user = ""
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        if m["role"] == "user":
            last_user = m["content"]
        if history or m["role"] != "user":
            history.append({"role": role, "parts": [m["content"]]})

    if DEBUG:
        print(f"[danphe debug] gemini flash history={len(history)}")

    chat = model.start_chat(history=history[:-1] if history else [])
    response = chat.send_message(last_user or messages[-1]["content"], stream=True)

    for chunk in response:
        if chunk.text:
            yield chunk.text


def complete(messages: list[dict], system: str = "") -> str:
    return "".join(stream(messages, system=system))
