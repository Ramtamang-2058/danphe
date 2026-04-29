"""
agent.py — agentic loop: think → tool call → observe → repeat until done.

The agent sends a prompt, receives a response, applies any patches/commands,
feeds results back, and loops until the LLM says DONE or produces no actions.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterator

from danphe import config, router
from danphe.patches import extract_patches, extract_bash, apply_patches
from danphe.config import load_claude_md, load_skills
from tools.file_tool import project_tree, read_files, collect_project_files

MAX_ITERATIONS = 8  # safety cap on agentic loops

# ── System prompt ─────────────────────────────────────────────────────────────

_BASE_SYSTEM = """\
You are Danphe, an agentic developer assistant running in the terminal.
You can read files, write files, and run shell commands.

When you want to create or edit a file, use this format:
```python
# FILE: path/to/file.py
<complete file content here>
```

When you want to run a shell command, use:
```bash
<command here>
```

Rules:
- Always provide the complete file content when patching (not just diffs).
- After applying fixes, you will see the command output. Use it to verify.
- When the task is fully complete, include the word DONE in your response.
- If you cannot complete the task, explain why clearly.
- Be concise. Write code, not essays.
"""


def _build_system(cwd: Path) -> str:
    parts = [_BASE_SYSTEM]

    claude_md = load_claude_md(cwd)
    if claude_md:
        parts.append(f"\n## Project context (CLAUDE.md)\n{claude_md}")

    skills = load_skills()
    if skills:
        skill_text = "\n\n".join(f"### Skill: {k}\n{v}" for k, v in skills.items())
        parts.append(f"\n## Skills\n{skill_text}")

    return "\n".join(parts)


def _build_initial_prompt(task: str, files: list[str], cwd: Path) -> str:
    parts = []

    # Project tree for context
    tree = project_tree(cwd)
    parts.append(f"## Project structure\n{tree}")

    # Attached files
    if files:
        content = read_files(files)
        parts.append(f"## Attached files\n{content}")

    parts.append(f"## Task\n{task}")
    return "\n\n".join(parts)


# ── Streaming helpers ─────────────────────────────────────────────────────────

def _stream_response(messages: list[dict]) -> tuple[str, str, str]:
    """
    Pick backend + model, stream response.
    Returns (full_response, backend, tier).
    """
    backend, tier = router.pick(messages)

    if backend == "nvidia":
        from danphe.llm.nvidia import stream
        chunks = stream(messages, model_tier=tier)
    elif backend == "gemini":
        system = messages[0]["content"] if messages[0]["role"] == "system" else ""
        user_msgs = [m for m in messages if m["role"] != "system"]
        from danphe.llm.gemini import stream
        chunks = stream(user_msgs, system=system)
    else:
        raise RuntimeError("devloop backend not implemented in agent (use CLI directly)")

    full = ""
    for chunk in chunks:
        print(chunk, end="", flush=True)
        full += chunk
    print()  # newline after streaming ends
    return full, backend, tier


# ── Main agent loop ───────────────────────────────────────────────────────────

def run_task(
    task: str,
    files: list[str] | None = None,
    cwd: Path | None = None,
    max_iter: int = MAX_ITERATIONS,
) -> str:
    """
    Run an agentic task.
    Returns the final response text.
    """
    cwd = cwd or Path.cwd()
    files = files or []

    system = _build_system(cwd)
    initial_prompt = _build_initial_prompt(task, files, cwd)

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user",   "content": initial_prompt},
    ]

    last_response = ""

    for iteration in range(1, max_iter + 1):
        backend, tier = router.pick(messages)
        model_label = router.describe(backend, tier)

        if config.DEBUG or iteration > 1:
            print(f"\n[danphe] iteration {iteration}/{max_iter} · {model_label}\n")

        response, backend, tier = _stream_response(messages)
        last_response = response

        # Check for completion
        if "DONE" in response.upper():
            break

        # Try to apply patches + commands
        patches = extract_patches(response)
        commands = extract_bash(response)

        if not patches and not commands:
            # No actions — LLM is just talking, we're done
            break

        # Apply and collect results
        result = apply_patches(response, str(cwd))

        # Build feedback message
        feedback_parts = []
        if result.patched:
            feedback_parts.append(f"Patched files: {', '.join(result.patched)}")
        for cmd_result in result.commands:
            feedback_parts.append(
                f"$ {cmd_result['cmd']}\n"
                f"exit code: {cmd_result['rc']}\n"
                f"{cmd_result['output']}"
            )

        if not feedback_parts:
            break

        feedback = "\n\n".join(feedback_parts)
        if not result.success:
            feedback += "\n\nSome steps failed. Please fix the errors above."

        # Add to conversation and loop
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user",      "content": feedback})

        if result.success and "DONE" in response.upper():
            break

    return last_response


# ── Single-shot ask (no agentic loop) ────────────────────────────────────────

def ask(
    question: str,
    files: list[str] | None = None,
    cwd: Path | None = None,
) -> Iterator[str]:
    """
    Single-turn ask — streams the answer, no patch-apply loop.
    Yields text chunks.
    """
    cwd = cwd or Path.cwd()
    files = files or []

    system = _build_system(cwd)
    prompt_parts = []

    if files:
        prompt_parts.append(f"## Attached files\n{read_files(files)}")
    prompt_parts.append(f"## Question\n{question}")

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": "\n\n".join(prompt_parts)},
    ]

    backend, tier = router.pick(messages)

    if backend == "nvidia":
        from danphe.llm.nvidia import stream
        yield from stream(messages, model_tier=tier)
    elif backend == "gemini":
        user_msgs = [m for m in messages if m["role"] != "system"]
        from danphe.llm.gemini import stream
        yield from stream(user_msgs, system=system)
    else:
        yield "[devloop bridge: use `danphe run` for browser-based fallback]"
