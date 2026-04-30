"""
cli.py — danphe interactive REPL + Click entry point.

  danphe                     # interactive REPL (default)
  danphe ask "question"      # single Q&A, streamed
  danphe run "task"          # agentic task
  danphe models              # show model routing

REPL slash commands:
  /help   /clear  /compact  /model  /cost
  /add <file>     /instagram          /exit
"""
from __future__ import annotations
import os
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from danphe import config, router, ui
from danphe.config import load_claude_md, load_skills

console = ui.console

# ── Slash-command completer ────────────────────────────────────────────────────

_SLASH_CMDS = [
    "/help", "/clear", "/compact", "/model", "/cost",
    "/add", "/instagram", "/exit",
]


class _ReplCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            word = text.split()[0] if text.split() else "/"
            for cmd in _SLASH_CMDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
        elif text.startswith("@"):
            # @file completion from cwd
            partial = text[1:]
            for p in sorted(Path.cwd().glob(partial + "*")):
                yield Completion(p.name, start_position=-len(partial))


# ── Key bindings (Esc+Enter = newline) ────────────────────────────────────────

_kb = KeyBindings()


@_kb.add("escape", "enter")
def _insert_newline(event):
    event.current_buffer.insert_text("\n")


# ── Banner ─────────────────────────────────────────────────────────────────────

def _banner() -> None:
    cwd = Path.cwd()
    has_nv = bool(config.NVIDIA_API_KEY)
    has_gm = bool(config.GEMINI_API_KEY)
    claude_md = load_claude_md(cwd)
    skills = load_skills()

    backend_parts: list[str] = []
    if has_nv:
        _, tier = router.pick([{"role": "user", "content": "hi"}])
        backend_parts.append(f"[green]NVIDIA[/green] [dim]({tier})[/dim]")
    if has_gm:
        backend_parts.append("[green]Gemini[/green]")
    if not backend_parts:
        backend_parts.append("[yellow]no API keys[/yellow]")

    status_parts = [f"[dim]{cwd}[/dim]"]
    if claude_md:
        status_parts.append("[green]CLAUDE.md[/green]")
    if skills:
        status_parts.append(f"[cyan]skills: {', '.join(skills)}[/cyan]")

    console.print(
        Panel(
            Text.from_markup(
                "[bold cyan]danphe[/bold cyan] [dim]— agentic dev CLI[/dim]\n"
                + "  ".join(status_parts)
                + "\n[dim]backends:[/dim] "
                + "  ".join(backend_parts)
            ),
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print(
        "[dim]  /help for commands  ·  Esc+Enter for newline  ·  Ctrl+D to exit[/dim]\n"
    )


# ── @file resolution ───────────────────────────────────────────────────────────

def _resolve_at_files(text: str) -> tuple[str, str]:
    """
    Parse @filename tokens from text. Returns (cleaned_text, file_context).
    file_context is prepended file contents ready for the prompt.
    """
    import re

    tokens = re.findall(r"@(\S+)", text)
    if not tokens:
        return text, ""

    context_parts: list[str] = []
    for token in tokens:
        p = Path(token)
        if p.exists() and p.is_file():
            try:
                content = p.read_text(errors="replace")
                context_parts.append(f"# FILE: {token}\n{content}")
                text = text.replace(f"@{token}", f"`{token}`")
            except Exception:
                pass

    context = "\n\n".join(context_parts)
    return text, context


# ── Agent runner with animated display ────────────────────────────────────────

def _run_agent(user_input: str, session: list[dict], cwd: Path) -> str:
    """
    Send user_input through the agent loop.
    Shows mist animation while thinking, streams text as it arrives,
    shows tool calls inline.
    Returns final response text.
    """
    from danphe import agent

    q: Queue = Queue()
    done_event = threading.Event()

    def on_text(chunk: str) -> None:
        q.put(("text", chunk))

    def on_tool(name: str, args: dict, result: str, ok: bool) -> None:
        q.put(("tool", name, args, result, ok))

    def _agent_thread() -> None:
        try:
            agent.run(session, cwd=cwd, on_text=on_text, on_tool=on_tool)
        except Exception as e:
            q.put(("error", str(e)))
        finally:
            done_event.set()

    thread = threading.Thread(target=_agent_thread, daemon=True)
    thread.start()

    thinking_display = ui._Thinking("thinking")
    text_parts: list[str] = []
    first_output = False

    console.print()

    with Live(
        thinking_display,
        refresh_per_second=22,
        transient=True,
        console=console,
    ) as live:
        while not (done_event.is_set() and q.empty()):
            try:
                item = q.get(timeout=0.05)
            except Empty:
                continue

            kind = item[0]

            # First output: stop mist, switch to normal console
            if not first_output:
                first_output = True
                live.stop()

            if kind == "text":
                chunk: str = item[1]
                text_parts.append(chunk)
                console.print(chunk, end="", markup=False, highlight=False)

            elif kind == "tool":
                _, name, args, result, ok = item
                # Blank line before tool block if text was streaming
                if text_parts and not text_parts[-1].endswith("\n"):
                    console.print()
                console.print()
                ui.show_tool(name, args)
                ui.show_result(result, ok)

            elif kind == "error":
                console.print(f"\n[red]Error: {item[1]}[/red]")

    if text_parts:
        console.print()

    thread.join(timeout=10)
    return "".join(text_parts)


def _stream_ask(user_input: str, session: list[dict], cwd: Path) -> str:
    """Stream a simple Q&A answer with mist animation until first token."""
    from danphe import agent as ag

    text_parts: list[str] = []
    first_token = threading.Event()
    q: Queue = Queue()
    done_event = threading.Event()

    def _thread():
        try:
            for chunk in ag.stream_ask(user_input, cwd=cwd):
                q.put(chunk)
                first_token.set()
        finally:
            done_event.set()

    t = threading.Thread(target=_thread, daemon=True)
    t.start()

    thinking_display = ui._Thinking("thinking")
    console.print()

    with Live(thinking_display, refresh_per_second=22, transient=True, console=console) as live:
        while not (done_event.is_set() and q.empty()):
            try:
                chunk = q.get(timeout=0.05)
            except Empty:
                continue
            live.stop()
            text_parts.append(chunk)
            console.print(chunk, end="", markup=False, highlight=False)

    console.print()
    t.join(timeout=10)
    full = "".join(text_parts)
    session.append({"role": "assistant", "content": full})
    return full


# ── Slash command handlers ─────────────────────────────────────────────────────

def _cmd_help() -> None:
    console.print(
        Panel(
            "[bold]Slash commands[/bold]\n"
            "  [cyan]/help[/cyan]          Show this help\n"
            "  [cyan]/clear[/cyan]         Clear conversation history\n"
            "  [cyan]/compact[/cyan]       Summarise history to save context\n"
            "  [cyan]/model[/cyan]         Show current model routing\n"
            "  [cyan]/cost[/cyan]          Estimate token usage\n"
            "  [cyan]/add [dim]<path>[/dim][/cyan]     Add a file to context\n"
            "  [cyan]/instagram[/cyan]     Launch Instagram/WhatsApp automation\n"
            "  [cyan]/exit[/cyan]          Exit (also Ctrl+D)\n\n"
            "[bold]Input tricks[/bold]\n"
            "  [cyan]@file.py[/cyan]       Inline file contents in your message\n"
            "  [cyan]Esc+Enter[/cyan]      Insert a newline (multi-line input)\n"
            "  [cyan]Ctrl+C[/cyan]         Cancel (at prompt) / interrupt\n"
            "  [cyan]Ctrl+D[/cyan]         Exit\n\n"
            "[bold]Model is auto-picked[/bold] based on token count.\n"
            "Override with [cyan]DANPHE_MODEL=fast|long|reasoning|gemini[/cyan] in .env",
            border_style="dim",
            title="[cyan]danphe help[/cyan]",
        )
    )


def _cmd_model(session: list[dict]) -> None:
    content = " ".join(
        m.get("content", "") for m in session if isinstance(m.get("content"), str)
    ) or "hello"
    backend, tier = router.pick([{"role": "user", "content": content}])
    label = router.describe(backend, tier)
    tok = sum(len(m.get("content", "")) for m in session if isinstance(m.get("content"), str)) // 4
    console.print(f"  [dim]route:[/dim] [cyan]{label}[/cyan]  [dim]est. {tok} tokens in session[/dim]")


def _cmd_cost(session: list[dict]) -> None:
    total_chars = sum(
        len(m.get("content", "")) for m in session if isinstance(m.get("content"), str)
    )
    tok = total_chars // 4
    msgs = len(session)
    if tok < 1000:
        tok_str = str(tok)
    elif tok < 1_000_000:
        tok_str = f"{tok / 1000:.1f}k"
    else:
        tok_str = f"{tok / 1_000_000:.2f}M"
    console.print(
        f"  [dim]messages:[/dim] {msgs}  "
        f"[dim]est. tokens:[/dim] [cyan]{tok_str}[/cyan]  "
        f"[dim]chars:[/dim] {total_chars:,}"
    )


def _cmd_compact(session: list[dict], cwd: Path) -> None:
    if len(session) < 4:
        console.print("[dim]Nothing to compact yet[/dim]")
        return

    from danphe.llm import nvidia, gemini as gm

    summary_msgs = list(session) + [
        {"role": "user", "content": (
            "Please summarise the above conversation in 3-4 concise paragraphs. "
            "Focus on: what was accomplished, key decisions, any important file paths "
            "or findings, and open questions. This summary will replace the full history."
        )}
    ]

    summary = ""
    with ui.thinking("compacting..."):
        backend, tier = router.pick(session)
        if backend == "nvidia":
            summary = nvidia.complete(summary_msgs, model_tier=tier)
        else:
            user_msgs = [m for m in summary_msgs if m.get("role") != "system"]
            summary = gm.complete(user_msgs)

    old_count = len(session)
    session.clear()
    session.extend([
        {"role": "user", "content": f"[Conversation summary]\n{summary}"},
        {"role": "assistant", "content": "Understood — I'll continue from this summary."},
    ])
    console.print(
        f"  [green]Compacted[/green] [dim]{old_count} messages → 2 (summary)[/dim]"
    )


def _cmd_add(args: list[str], session: list[dict]) -> None:
    if not args:
        console.print("[yellow]Usage: /add <file_or_dir>[/yellow]")
        return
    for path_str in args:
        p = Path(path_str)
        if not p.exists():
            console.print(f"  [red]Not found:[/red] {path_str}")
            continue
        if p.is_file():
            try:
                content = p.read_text(errors="replace")
                session.append({
                    "role": "user",
                    "content": f"[Added file: {path_str}]\n```\n{content}\n```",
                })
                session.append({"role": "assistant", "content": f"Got it — I've read `{path_str}`."})
                console.print(f"  [green]+[/green] [dim]{path_str}[/dim] added to context")
            except Exception as e:
                console.print(f"  [red]Error reading {path_str}:[/red] {e}")
        else:
            console.print(f"  [yellow]{path_str} is a directory — use @dir pattern in your message[/yellow]")


def _cmd_instagram() -> None:
    """Launch the Instagram/WhatsApp automation."""
    project_root = Path(__file__).parent.parent
    candidates = [
        project_root / "instra-automate" / "msg.py",
        project_root / "instra-automate" / "send_dm.py",
    ]
    script = next((c for c in candidates if c.exists()), None)
    if script is None:
        console.print("[red]Instagram automation not found in instra-automate/[/red]")
        return
    import subprocess
    console.print(f"  [cyan]Launching[/cyan] [dim]{script}[/dim]\n")
    subprocess.run([sys.executable, str(script)], cwd=str(script.parent))


# ── Main REPL ──────────────────────────────────────────────────────────────────

def repl() -> None:
    _banner()

    cwd = Path.cwd()
    session: list[dict] = []

    history_file = Path.home() / ".danphe_history"
    pt = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=_ReplCompleter(),
        key_bindings=_kb,
        complete_while_typing=False,
    )

    while True:
        try:
            raw = pt.prompt(HTML("<ansicyan><b>❯ </b></ansicyan>"))
        except KeyboardInterrupt:
            console.print("[dim]  (Ctrl+C — type /exit or Ctrl+D to quit)[/dim]")
            continue
        except EOFError:
            console.print("[dim]bye[/dim]")
            break

        line = raw.strip()
        if not line:
            continue

        # ── Slash commands ─────────────────────────────────────────────────────
        if line.startswith("/"):
            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("/exit", "/quit", "/q"):
                console.print("[dim]bye[/dim]")
                break
            elif cmd == "/help":
                _cmd_help()
            elif cmd == "/clear":
                session.clear()
                console.print("[dim]Conversation cleared.[/dim]")
            elif cmd == "/compact":
                _cmd_compact(session, cwd)
            elif cmd == "/model":
                _cmd_model(session)
            elif cmd == "/cost":
                _cmd_cost(session)
            elif cmd == "/add":
                _cmd_add(args, session)
            elif cmd == "/instagram":
                _cmd_instagram()
            else:
                console.print(f"[yellow]Unknown command: {cmd}  (try /help)[/yellow]")
            continue

        # ── @file mentions ─────────────────────────────────────────────────────
        line, file_context = _resolve_at_files(line)

        if file_context:
            user_content = f"{file_context}\n\n{line}"
        else:
            user_content = line

        session.append({"role": "user", "content": user_content})

        # ── Route: agentic (has tools) vs quick ask ────────────────────────────
        backend, tier = router.pick(session)
        label = router.describe(backend, tier)
        console.print(f"\n  [dim]{label}[/dim]")

        _run_agent(line, session, cwd)

        console.print()


# ── Click sub-commands ─────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Danphe — agentic dev CLI powered by NVIDIA NIM + Gemini."""
    if ctx.invoked_subcommand is None:
        repl()


@main.command()
@click.argument("question", nargs=-1, required=True)
@click.option("-f", "--file", "files", multiple=True, help="Attach file(s)")
def ask(question: tuple[str, ...], files: tuple[str, ...]) -> None:
    """Single-turn question answered with streaming."""
    from danphe import agent as ag

    q = " ".join(question)
    cwd = Path.cwd()
    console.print()
    for chunk in ag.stream_ask(q, files=list(files) or None, cwd=cwd):
        console.print(chunk, end="", markup=False, highlight=False)
    console.print()


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.option("-f", "--file", "files", multiple=True, help="Attach file(s)")
@click.option("--max-iter", default=10, show_default=True, help="Max agentic iterations")
def run(task: tuple[str, ...], files: tuple[str, ...], max_iter: int) -> None:
    """Agentic task — reads/writes files, runs commands, loops until done."""
    from danphe import agent as ag

    t = " ".join(task)
    cwd = Path.cwd()
    session: list[dict] = []

    if files:
        from tools.file_tool import read_files
        ctx = read_files(list(files))
        session.append({"role": "user", "content": ctx})
        session.append({"role": "assistant", "content": "Got it."})

    session.append({"role": "user", "content": t})
    label = router.describe(*router.pick(session))
    console.print(f"\n  [dim]{label}[/dim]")
    _run_agent(t, session, cwd)


@main.command()
def models() -> None:
    """Show available models and current routing."""
    from danphe.llm.nvidia import MODELS as nv

    console.print("\n[bold]NVIDIA NIM (free tier):[/bold]")
    for tier, mid in nv.items():
        console.print(f"  [cyan]{tier:12}[/cyan] {mid}")
    console.print("\n[bold]Fallback:[/bold]")
    console.print("  [cyan]gemini      [/cyan] gemini-2.0-flash (free)")
    console.print()

    backend, tier = router.pick([{"role": "user", "content": "hi"}])
    console.print(f"[bold]Active route:[/bold] [cyan]{router.describe(backend, tier)}[/cyan]")

    if not config.NVIDIA_API_KEY:
        console.print("[yellow]  ⚠  NVIDIA_API_KEY not set[/yellow]")
    if not config.GEMINI_API_KEY:
        console.print("[yellow]  ⚠  GEMINI_API_KEY not set[/yellow]")
    console.print()


if __name__ == "__main__":
    main()
