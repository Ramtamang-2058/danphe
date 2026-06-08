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
You have tools: read_file, write_file, run_bash, list_files, search_code, list_skills, read_skill.

CRITICAL: You MUST use tools to perform actions. Never tell the user to run a command themselves \
unless they explicitly ask for the command syntax. If the user asks you to do something — \
checkout a branch, start docker, run tests, install packages, etc. — use run_bash to do it.

SKILL CHECK RULE: Before saying "I cannot do X" or refusing any request, \
ALWAYS call list_skills first. If a skill matches, call read_skill to get its full \
instructions and follow them. Only refuse after confirming no skill covers the request.

TOKEN AWARENESS: Models are routed by token count automatically. \
Keep responses concise. If context grows large, suggest /compact to the user.

Examples of correct behavior:
- "checkout to develop branch" → run_bash("git checkout develop && git pull origin develop")
- "start docker" → run_bash("sudo systemctl start docker" or "docker compose up -d")
- "run tests" → run_bash("pytest" or whatever test runner applies)
- "do yourself" → use the appropriate tool, do not explain or defer
- "reply to Amod on instagram" → user wants /instagram command with continuous mode

Available CLI commands (tell user about these when relevant):
- /instagram  - Instagram: send DM, read history, auto-reply, or continuous loop
- /help       - Show all available commands
- /model      - Switch AI models
- /clear      - Clear conversation history
- /compact    - Summarize conversation to save tokens
- /skills     - List available skills

Guidelines:
- Act immediately — read files before modifying, run commands before reporting results.
- Write complete file content when using write_file.
- After running commands, show output and explain what it means.
- Be concise. Prefer action over explanation.
- When done, give a one-line summary of what changed.
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

    Resilient to network errors — tool results are persisted even if streaming fails.
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
        try:
            if backend == "nvidia":
                events = nvidia.stream_with_tools(
                    messages,
                    model_tier=tier,
                    system=system,
                    tools=tool_lib.SCHEMAS,
                )
            elif backend == "gemini":
                events = gm.stream_with_tools(
                    messages,
                    system=system,
                    tools=tool_lib.SCHEMAS,
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
        except (IOError, RuntimeError, BrokenPipeError) as e:
            # Network error — report and allow recovery
            err_msg = f"\n[Network error in iteration {iteration + 1}: {e}. Continuing with available tools or context.]"
            text_this_turn += err_msg
            if on_text:
                on_text(err_msg)
        except Exception as e:
            # Unexpected error — report and break
            err_msg = f"\n[Unexpected error in iteration {iteration + 1}: {e}]"
            text_this_turn += err_msg
            if on_text:
                on_text(err_msg)

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
            try:
                result = tool_lib.execute(tc["name"], tc["args"])
                ok = not result.startswith("Error")

                if on_tool:
                    on_tool(tc["name"], tc["args"], result, ok)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })
            except Exception as e:
                # Tool execution error
                error_result = f"Error executing {tc['name']}: {e}"
                if on_tool:
                    on_tool(tc["name"], tc["args"], error_result, False)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": error_result,
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
        for kind, data in gm.stream_with_tools(messages, system=system, tools=tool_lib.SCHEMAS):
            if kind == "text":
                yield data
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
