"""
agent.py — tool-calling agentic loop.

Flow per turn:
  1. Send messages + tool schemas to LLM (streaming)
  2. Yield text chunks live via on_text callback
  3. After stream ends: execute any tool calls, add results to messages
  4. Repeat until no tool calls in response (or max_iter reached)
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable

from danphe import router
from danphe.config import load_claude_md
from danphe import tools as tool_lib

MAX_ITER = 10

_BASE_SYSTEM = """\
You are Danphe, an agentic developer assistant running in the terminal.
You have tools to read files, write files, run shell commands, list directories, \
and search code. You also have access to specialized skills via the list_skills and read_skill tools.

Available CLI commands you can suggest to users:
- /instagram - Send Instagram messages (username or display name)
- /help - Show all available commands
- /model - Switch AI models
- /clear - Clear conversation history
- /compact - Summarize conversation to save tokens

Guidelines:
- Use tools proactively — read relevant files before modifying them.
- Write complete file content when using write_file (no partial patches).
- After running tests or commands, show the output and explain what it means.
- Be concise. Prefer action over explanation.
- When the task is fully done, give a short summary of what changed.
"""


def _build_system(cwd: Path) -> str:
    parts = [_BASE_SYSTEM]
    claude_md = load_claude_md(cwd)
    if claude_md:
        parts.append(f"\n## Project context (CLAUDE.md)\n{claude_md}")
    return "\n".join(parts)


def run(
    messages: list[dict],
    cwd: Path | None = None,
    on_text: Callable[[str], None] | None = None,
    on_tool: Callable[[str, dict, str, bool], None] | None = None,
    max_iter: int = MAX_ITER,
) -> str:
    """
    Run the tool-calling agentic loop.

    messages  — conversation history, modified in-place (tool calls + responses appended)
    on_text   — called with each streamed text chunk: on_text(chunk)
    on_tool   — called after each tool execution: on_tool(name, args, result, ok)
    Returns   — final response text (last assistant message)
    """
    from danphe.llm import nvidia, gemini as gm

    cwd = cwd or Path.cwd()
    system = _build_system(cwd)
    backend, tier = router.pick(messages)
    final_text = ""

    for iteration in range(max_iter):
        tool_calls_this_turn: list[dict] = []
        text_this_turn = ""

        # ── Stream response ────────────────────────────────────────────────────
        if backend == "nvidia":
            events = nvidia.stream_with_tools(
                messages,
                model_tier=tier,
                system=system,
                tools=tool_lib.SCHEMAS,
            )
        elif backend == "gemini":
            # Gemini fallback — no native tool calling; plain stream
            user_msgs = [m for m in messages if m.get("role") != "system"]
            events = (
                ("text", chunk)
                for chunk in gm.stream(user_msgs, system=system)
            )
        else:
            # Devloop bridge fallback
            import subprocess
            user_msgs = [m for m in messages if m.get("role") != "system"]
            q = user_msgs[-1]["content"] if user_msgs else ""
            
            def _stream_devloop():
                try:
                    process = subprocess.Popen(["devloop", "ask", q], stdout=subprocess.PIPE, text=True)
                    for line in process.stdout:
                        yield ("text", line)
                    process.wait()
                except Exception as e:
                    yield ("text", f"devloop bridge error: {e}")
            events = _stream_devloop()

        for kind, data in events:
            if kind == "text":
                text_this_turn += data
                if on_text:
                    on_text(data)
            elif kind == "tool_call":
                tool_calls_this_turn.append(data)

        final_text = text_this_turn

        # ── No tool calls → done ───────────────────────────────────────────────
        if not tool_calls_this_turn:
            # Persist the final assistant message
            if text_this_turn:
                messages.append({"role": "assistant", "content": text_this_turn})
            break

        # ── Add assistant message that contains tool_calls ─────────────────────
        messages.append({
            "role": "assistant",
            "content": text_this_turn,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in tool_calls_this_turn
            ],
        })

        # ── Execute tools, add results ─────────────────────────────────────────
        for tc in tool_calls_this_turn:
            result = tool_lib.execute(tc["name"], tc["args"])
            ok = not result.startswith("Error")

            if on_tool:
                on_tool(tc["name"], tc["args"], result, ok)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return final_text


def stream_ask(
    question: str,
    files: list[str] | None = None,
    cwd: Path | None = None,
):
    """
    Single-turn Q&A (no tool loop). Yields text chunks for streaming display.
    """
    from danphe.llm import nvidia, gemini as gm
    from tools.file_tool import read_files  # existing helper

    cwd = cwd or Path.cwd()
    system = _build_system(cwd)

    parts: list[str] = []
    if files:
        parts.append(read_files(files))
    parts.append(question)

    messages = [{"role": "user", "content": "\n\n".join(parts)}]
    backend, tier = router.pick(messages)

    if backend == "nvidia":
        for kind, data in nvidia.stream_with_tools(messages, model_tier=tier, system=system):
            if kind == "text":
                yield data
    elif backend == "gemini":
        user_msgs = [m for m in messages if m.get("role") != "system"]
        yield from gm.stream(user_msgs, system=system)
    else:
        # Devloop bridge
        import subprocess
        user_msgs = [m for m in messages if m.get("role") != "system"]
        q = user_msgs[-1]["content"] if user_msgs else ""
        try:
            process = subprocess.Popen(["devloop", "ask", q], stdout=subprocess.PIPE, text=True)
            for line in process.stdout:
                yield line
            process.wait()
        except Exception as e:
            yield f"devloop bridge error: {e}\n"
