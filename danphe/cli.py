"""
cli.py — danphe entry point.

Usage:
  danphe                        # interactive REPL
  danphe ask "what does X do"   # single question
  danphe run "fix the tests"    # agentic task (loops until done)
  danphe run "fix X" -f src/    # attach files
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich import print as rprint

from danphe import config, router
from danphe.config import load_claude_md, load_skills

console = Console()

LOGO = """[bold purple]danphe[/bold purple] [dim]— agentic dev CLI[/dim]"""

HELP_TEXT = """\
[bold]Just type — no prefix needed (like Claude Code):[/bold]
  [cyan]what does X do[/cyan]           → Q&A, streamed
  [cyan]fix the bug in api.py[/cyan]    → agentic: reads/patches/loops
  [cyan]create a migration for Y[/cyan] → agentic: writes files + runs cmds
  [cyan]anything -f file dir/[/cyan]    → attach files, always agentic

[bold]Built-ins:[/bold]
  [cyan]model[/cyan]  [cyan]tree[/cyan]  [cyan]clear[/cyan]  [cyan]exit[/cyan] / [cyan]quit[/cyan] / Ctrl-D
"""


# ── Formatting helpers ────────────────────────────────────────────────────────

def print_header():
    console.print(Panel(
        Text.from_markup(LOGO),
        border_style="purple",
        padding=(0, 2),
    ))
    cwd = Path.cwd()
    claude_md = load_claude_md(cwd)
    skills = load_skills()

    hints = [f"[dim]cwd:[/dim] {cwd}"]
    if claude_md:
        hints.append("[dim]CLAUDE.md:[/dim] [green]loaded[/green]")
    if skills:
        hints.append(f"[dim]skills:[/dim] [green]{', '.join(skills.keys())}[/green]")

    has_nv = bool(config.NVIDIA_API_KEY)
    has_gm = bool(config.GEMINI_API_KEY)
    backends = []
    if has_nv:
        backends.append("[green]NVIDIA[/green]")
    if has_gm:
        backends.append("[green]Gemini[/green]")
    if not backends:
        backends.append("[yellow]devloop (no API keys)[/yellow]")
    hints.append(f"[dim]backends:[/dim] {' · '.join(backends)}")

    console.print("  " + "  ".join(hints))
    console.print()


def print_model_info(messages: list[dict]):
    backend, tier = router.pick(messages)
    label = router.describe(backend, tier)
    console.print(f"[dim]  model → {label}[/dim]")


def stream_and_render(chunks, markdown: bool = True):
    """Stream chunks from agent, print with optional markdown render."""
    full = ""
    # Stream raw for responsiveness
    for chunk in chunks:
        print(chunk, end="", flush=True)
        full += chunk
    print()

    # Re-render as markdown if it looks like markdown
    if markdown and any(c in full for c in ["```", "##", "**", "- ", "1. "]):
        console.print()
        console.print(Markdown(full))

    return full


def _parse_run_args(parts: list[str]) -> tuple[str, list[str]]:
    """Parse 'task -f file1 file2' from a list of tokens."""
    task_parts, files = [], []
    i = 0
    while i < len(parts):
        if parts[i] == "-f" and i + 1 < len(parts):
            i += 1
            while i < len(parts) and not parts[i].startswith("-"):
                files.append(parts[i])
                i += 1
        else:
            task_parts.append(parts[i])
            i += 1
    return " ".join(task_parts), files


# ── REPL ─────────────────────────────────────────────────────────────────────

def repl():
    print_header()
    console.print(Markdown(HELP_TEXT.replace("[bold]", "**").replace("[/bold]", "**")
                           .replace("[cyan]", "`").replace("[/cyan]", "`")))

    history: list[dict] = []
    cwd = Path.cwd()

    while True:
        try:
            line = Prompt.ask("\n[bold purple]danphe[/bold purple]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        rest = parts[1:]

        # ── built-in commands ──────────────────────────────────────────────
        if cmd in ("exit", "quit", "q"):
            console.print("[dim]bye[/dim]")
            break

        if cmd == "clear":
            history.clear()
            console.print("[dim]conversation cleared[/dim]")
            continue

        if cmd == "tree":
            from tools.file_tool import project_tree
            console.print(project_tree(cwd))
            continue

        if cmd == "model":
            print_model_info(history or [{"role": "user", "content": "test"}])
            continue

        if cmd == "help":
            console.print(Markdown(HELP_TEXT.replace("[bold]", "**").replace("[/bold]", "**")
                                   .replace("[cyan]", "`").replace("[/cyan]", "`")))
            continue

        # ── explicit -f flag: always agentic with files ──────────────────
        if "-f" in parts:
            task, files = _parse_run_args(parts)
            label = router.describe(*router.pick([{"role": "user", "content": task}]))
            console.print(f"\n[dim]⚙  {label}[/dim]\n")
            from danphe.agent import run_task
            run_task(task, files=files or None, cwd=cwd)
            continue

        # ── auto-decide: agentic if action verb, else Q&A ────────────────
        # Just type naturally — no ask/run prefix needed (like Claude Code)
        _AGENTIC_WORDS = {
            "fix", "create", "refactor", "edit", "update", "add", "remove",
            "delete", "rename", "move", "write", "implement", "make", "change",
            "run", "execute", "install", "build", "test", "debug", "patch",
        }
        is_agentic = parts[0].lower() in _AGENTIC_WORDS if parts else False
        label = router.describe(*router.pick([{"role": "user", "content": line}]))

        if is_agentic:
            console.print(f"\n[dim]⚙  {label}[/dim]\n")
            from danphe.agent import run_task
            run_task(line, cwd=cwd)
        else:
            console.print(f"\n[dim]◆  {label}[/dim]\n")
            from danphe.agent import ask as agent_ask
            stream_and_render(agent_ask(line, cwd=cwd))


# ── Click subcommands ─────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Danphe — agentic dev CLI."""
    if ctx.invoked_subcommand is None:
        repl()


@main.command()
@click.argument("question", nargs=-1, required=True)
@click.option("-f", "--files", multiple=True, help="Files or dirs to attach")
def ask(question, files):
    """Single-turn question, streamed answer."""
    from danphe.agent import ask as agent_ask
    q = " ".join(question)
    console.print(f"\n[dim]→ {router.describe(*router.pick([{'role':'user','content':q}]))}[/dim]\n")
    stream_and_render(agent_ask(q, files=list(files) or None))


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.option("-f", "--files", multiple=True, help="Files or dirs to attach")
@click.option("--max-iter", default=8, show_default=True, help="Max agentic iterations")
def run(task, files, max_iter):
    """Agentic task — reads/writes files, runs commands, loops until done."""
    from danphe.agent import run_task
    t = " ".join(task)
    console.print(f"\n[dim]→ {router.describe(*router.pick([{'role':'user','content':t}]))}[/dim]\n")
    run_task(t, files=list(files) or None, max_iter=max_iter)


@main.command()
def models():
    """Show available models and routing logic."""
    from danphe.llm.nvidia import MODELS as nv_models
    console.print("\n[bold]NVIDIA models (free tier):[/bold]")
    for tier, model in nv_models.items():
        console.print(f"  [cyan]{tier:10}[/cyan] {model}")
    console.print("\n[bold]Fallback:[/bold]")
    console.print("  [cyan]gemini    [/cyan] gemini-2.0-flash (free tier)")
    console.print("  [cyan]devloop   [/cyan] Claude.ai via Brave (no API key)")
    console.print()
    backend, tier = router.pick([{"role": "user", "content": "test"}])
    console.print(f"[bold]Current route:[/bold] {router.describe(backend, tier)}")
    if not config.NVIDIA_API_KEY:
        console.print("[yellow]  ⚠  NVIDIA_API_KEY not set[/yellow]")
    if not config.GEMINI_API_KEY:
        console.print("[yellow]  ⚠  GEMINI_API_KEY not set[/yellow]")


if __name__ == "__main__":
    main()