"""
cli.py — danphe interactive REPL + Click entry point.

  danphe                     # interactive REPL (default)
  danphe ask "question"      # single Q&A, streamed
  danphe run "task"          # agentic task
  danphe do "task"           # Claude browser bridge (no API tokens — survives quota)
  danphe social instagram @user --auto-reply  # social media automation
  danphe models              # show model routing

REPL slash commands:
  /help   /clear  /compact  /model  /cost
  /add <file>     /instagram     /skills     /exit
"""
from __future__ import annotations
import os
import sys
import threading
import time
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
    "/add", "/instagram", "/instragram", "/skills", "/exit",
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
    has_gq = bool(config.GROQ_API_KEY)
    claude_md = load_claude_md(cwd)
    skills = load_skills()

    backend_parts: list[str] = []
    if has_nv or has_gq:
        backend, tier = router.pick([{"role": "user", "content": "hi"}])
        backend_parts.append(f"[green]{router.describe(backend, tier)}[/green]")
    if not backend_parts:
        backend_parts.append("[yellow]no API keys — devloop bridge[/yellow]")

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

def _run_agent(user_input: str, session: list[dict], cwd: Path, label: str = "", max_iter: int = 10) -> str:
    """
    Send user_input through the agent loop.
    Shows mist animation while thinking, streams text as it arrives,
    shows tool calls inline. Returns final response text.
    """
    from danphe import agent

    q: Queue = Queue()
    done_event = threading.Event()

    def on_text(chunk: str) -> None:
        q.put(("text", chunk))

    def on_tool(name: str, args: dict, result: str, ok: bool, elapsed: float) -> None:
        q.put(("tool", name, args, result, ok, elapsed))

    def _agent_thread() -> None:
        try:
            agent.run(session, cwd=cwd, on_text=on_text, on_tool=on_tool, max_iter=max_iter)
        except Exception as e:
            q.put(("error", str(e)))
        finally:
            done_event.set()

    thread = threading.Thread(target=_agent_thread, daemon=True)
    thread.start()

    thinking_display = ui._Thinking("thinking")
    text_parts: list[str] = []
    first_output = False
    live_active = True

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
                live_active = False

            if kind == "text":
                if live_active:
                    live.stop()
                    live_active = False
                chunk: str = item[1]
                text_parts.append(chunk)
                console.print(chunk, end="", markup=False, highlight=False)

            elif kind == "tool":
                _, name, args, result, ok, elapsed = item
                # Blank line before tool block if text was streaming
                if text_parts and not text_parts[-1].endswith("\n"):
                    console.print()
                console.print()
                ui.show_tool(name, args, elapsed)
                ui.show_result(result, ok)
                # Agent is likely mid-loop — show mist again for the next LLM call
                if not done_event.is_set():
                    thinking_display.label = "thinking"
                    live.start()
                    live_active = True

            elif kind == "error":
                if live_active:
                    live.stop()
                    live_active = False
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
            "  [cyan]/instagram[/cyan]     Send Instagram message (username or display name)\n"
            "  [cyan]/skills[/cyan]        Show available skills\n"
            "  [cyan]/exit[/cyan]          Exit (also Ctrl+D)\n\n"
            "[bold]Available tools[/bold]\n"
            "  [cyan]read_file, write_file, run_bash, list_files, search_code[/cyan]\n"
            "  [cyan]list_skills, read_skill[/cyan] (for accessing skill knowledge base)\n"
            "  [cyan]browser_*[/cyan] (open/go/text/copy/type/click/press/screenshot/back/status/close)\n"
            "  [cyan]ipo_*[/cyan] (status/login/check/apply/submit/close — MeroShare)\n\n"
            "[bold]Input tricks[/bold]\n"
            "  [cyan]@file.py[/cyan]       Inline file contents in your message\n"
            "  [cyan]Esc+Enter[/cyan]      Insert a newline (multi-line input)\n"
            "  [cyan]Ctrl+C[/cyan]         Cancel (at prompt) / interrupt\n"
            "  [cyan]Ctrl+D[/cyan]         Exit\n\n"
            "[bold]Model is auto-picked[/bold] based on token count.\n"
            "Override with [cyan]DANPHE_MODEL=fast|long|reasoning|groq[/cyan] in .env",
            border_style="dim",
            title="[cyan]danphe help[/cyan]",
        )
    )


def _cmd_model(args: list[str], session: list[dict]) -> None:
    if args:
        target = args[0].lower().strip()
        if target in ["groq", "fast", "glm", "long", "deepseek", "reasoning", "nemotron", "devloop", "auto"]:
            config.FORCE_MODEL = "" if target == "auto" else target
            console.print(f"  [green]✓ Setup model routing to[/green] [cyan]{target}[/cyan]")
        else:
            console.print(f"  [yellow]Unknown model option: {target}. Valid: auto, groq, fast, long, reasoning, devloop[/yellow]")
        return

    content = " ".join(
        m.get("content", "") for m in session if isinstance(m.get("content"), str)
    ) or "hello"
    backend, tier = router.pick([{"role": "user", "content": content}])
    label = router.describe(backend, tier)
    tok = sum(len(m.get("content", "")) for m in session if isinstance(m.get("content"), str)) // 4
    console.print(f"  [dim]route:[/dim] [cyan]{label}[/cyan]  [dim]est. {tok} tokens in session[/dim]")
    console.print("  [dim]use /model <name> to switch (e.g. /model fast, /model long, /model auto)[/dim]")


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

    from danphe.llm import nvidia, groq as gq

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
        elif backend == "groq":
            summary = gq.complete(summary_msgs)
        else:
            summary = nvidia.complete(summary_msgs, model_tier="long")

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


def _load_instagram_contacts() -> dict[str, str]:
    """Load display-name → username map from ~/.danphe/instagram_contacts.json."""
    import json
    contacts_file = Path.home() / ".danphe" / "instagram_contacts.json"
    if contacts_file.exists():
        try:
            return json.loads(contacts_file.read_text())
        except Exception:
            pass
    return {}


def _resolve_instagram_target(name: str, contacts: dict[str, str]) -> str:
    """Return Instagram username for a display name, falling back to the name itself."""
    key = name.lower().strip().lstrip("@")
    # Exact match
    if key in contacts:
        return contacts[key]
    # Segment match: only match if the contact key equals a whole underscore-delimited
    # segment of the input (so "amod" matches "amod_xyz" but NOT "amodh_nepal")
    segments = key.split("_")
    for display, username in contacts.items():
        if display in segments:
            return username
    return name.lstrip("@")


def _cmd_instagram(args: list[str] | None = None) -> None:
    """Instagram automation: send, read, auto-reply once, or continuous loop."""
    project_root = Path(__file__).parent.parent
    social_script = project_root / "instra-automate" / "social_media.py"
    if not social_script.exists():
        console.print("[red]social_media.py not found in instra-automate/[/red]")
        return

    contacts = _load_instagram_contacts()
    contacts_hint = (
        f"  [dim]Known contacts: {', '.join(contacts.keys())}[/dim]\n"
        if contacts else
        f"  [dim]Tip: add contacts to ~/.danphe/instagram_contacts.json for name lookup[/dim]\n"
    )
    console.print(contacts_hint)

    try:
        raw_target = input("Who? (display name or @username): ").strip()
        if not raw_target:
            console.print("[red]Target cannot be empty.[/red]")
            return
        username = _resolve_instagram_target(raw_target, contacts)
        if username != raw_target.lstrip("@"):
            console.print(f"  [dim]Resolved '{raw_target}' → @{username}[/dim]")

        console.print(
            "\n  [bold]Modes:[/bold]\n"
            "  [cyan]1[/cyan]  Send a message\n"
            "  [cyan]2[/cyan]  Read conversation history\n"
            "  [cyan]3[/cyan]  Auto-reply once (LLM reads history, replies)\n"
            "  [cyan]4[/cyan]  Continuous loop (LLM watches + replies all day)\n"
        )
        mode = input("Choose mode [1-4]: ").strip()

        ai_model = "auto"
        personality = ""
        if mode in ("3", "4"):
            console.print(
                "\n  [bold]AI model:[/bold]\n"
                "  [cyan]1[/cyan]  auto  (Groq → NVIDIA) [default]\n"
                "  [cyan]2[/cyan]  groq  (Groq Llama 3.3 — fastest)\n"
                "  [cyan]3[/cyan]  nvidia  (NVIDIA — no quota)\n"
            )
            mc = input("Model [1-3, Enter=auto]: ").strip()
            ai_model = {"2": "groq", "3": "nvidia"}.get(mc, "auto")
            console.print(f"  [dim]Model: {ai_model}[/dim]")

            console.print(
                "\n  [bold]Personality[/bold] [dim](Enter to use default — casual Nepali guy)[/dim]\n"
                "  Examples:\n"
                "  [dim]• funny and sarcastic, roast them gently[/dim]\n"
                "  [dim]• friendly and warm like a close friend[/dim]\n"
                "  [dim]• flirty but respectful[/dim]\n"
                "  [dim]• very busy, short replies, a bit distracted[/dim]\n"
            )
            personality = input("Personality (or Enter for default): ").strip()
            if personality:
                console.print(f"  [dim]Personality: {personality}[/dim]")
    except KeyboardInterrupt:
        console.print("[dim]Cancelled.[/dim]")
        return

    import subprocess

    if mode == "1":
        try:
            message = input("Message: ").strip()
            if not message:
                console.print("[red]Message cannot be empty.[/red]")
                return
            confirm = input(f"Send to @{username}? (y/N): ").strip().lower()
            if confirm not in ("y", "yes"):
                console.print("[dim]Cancelled.[/dim]")
                return
        except KeyboardInterrupt:
            console.print("[dim]Cancelled.[/dim]")
            return
        # Use the legacy send_dm script if available, else social_media with a send approach
        send_script = project_root / "instra-automate" / "msg.py"
        if not send_script.exists():
            send_script = project_root / "instra-automate" / "send_dm.py"
        if send_script.exists():
            console.print(f"  [cyan]Sending to @{username}...[/cyan]\n")
            subprocess.run(
                [sys.executable, str(send_script), "instagram", username, message],
                cwd=str(send_script.parent),
            )
        else:
            console.print("[red]No send script found (msg.py / send_dm.py)[/red]")

    elif mode == "2":
        console.print(f"  [cyan]Reading conversation with @{username}...[/cyan]\n")
        subprocess.run(
            [sys.executable, str(social_script), "instagram", username],
            cwd=str(social_script.parent),
        )

    elif mode == "3":
        console.print(f"  [cyan]Auto-reply once to @{username} [{ai_model}]...[/cyan]\n")
        cmd = [
            sys.executable, str(social_script),
            "instagram", username,
            "--auto-reply",
            "--model", ai_model,
        ]
        if personality:
            cmd += ["--personality", personality]
        subprocess.run(cmd, cwd=str(social_script.parent))

    elif mode == "4":
        try:
            interval_str = input("Check interval in seconds [45]: ").strip()
            interval = int(interval_str) if interval_str.isdigit() else 45
        except KeyboardInterrupt:
            console.print("[dim]Cancelled.[/dim]")
            return
        console.print(
            f"  [cyan]Starting continuous loop for @{username} "
            f"(every {interval}s, model={ai_model}) — Ctrl+C to stop[/cyan]\n"
        )
        cmd = [
            sys.executable, str(social_script),
            "instagram", username,
            "--continuous",
            "--interval", str(interval),
            "--model", ai_model,
        ]
        if personality:
            cmd += ["--personality", personality]
        subprocess.run(cmd, cwd=str(social_script.parent))
    else:
        console.print("[yellow]Invalid choice.[/yellow]")


def _cmd_skills() -> None:
    """Show available skills."""
    from danphe.config import load_skills
    skills = load_skills()
    if not skills:
        console.print("[yellow]No skills available.[/yellow]")
        return
    
    console.print("[bold cyan]Available Skills:[/bold cyan]")
    for name, content in skills.items():
        # Get first line or first 100 chars as description
        first_line = content.split('\n', 1)[0].strip()
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."
        console.print(f"  [cyan]{name}[/cyan]: {first_line}")
    console.print(f"\n[dim]Use the list_skills tool for brief descriptions or read_skill tool for full content.[/dim]")


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
                _cmd_model(args, session)
            elif cmd == "/cost":
                _cmd_cost(session)
            elif cmd == "/add":
                _cmd_add(args, session)
            elif cmd in ("/instagram", "/instragram"):
                _cmd_instagram(args)
            elif cmd == "/skills":
                _cmd_skills()
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

        t0 = time.time()
        _run_agent(line, session, cwd)
        elapsed = time.time() - t0

        # Per-turn footer: model · elapsed · token estimate
        last = session[-1] if session else {}
        if last.get("role") == "assistant" and isinstance(last.get("content"), str):
            ui.reply_footer(label, elapsed, max(1, len(last["content"]) // 4))

        console.print()


# ── Click sub-commands ─────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Danphe — agentic dev CLI powered by NVIDIA NIM + Groq."""
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
    t0 = time.time()
    _run_agent(t, session, cwd, max_iter=max_iter)
    elapsed = time.time() - t0
    last = session[-1] if session else {}
    if last.get("role") == "assistant" and isinstance(last.get("content"), str):
        ui.reply_footer(label, elapsed, max(1, len(last["content"]) // 4))


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.option("-f", "--file", "files", multiple=True, help="Attach file(s)")
def do(task: tuple[str, ...], files: tuple[str, ...]) -> None:
    """Run via the Claude browser bridge (devloop) — no API tokens needed.

    Use this when API keys are exhausted / rate-limited. Opens Brave,
    asks Claude in the browser, and streams the answer.
    """
    import subprocess

    q = " ".join(task)
    console.print(
        Panel(
            "[bold]Browser bridge[/bold] — [cyan]Claude via Brave[/cyan], no API tokens used\n"
            f"[dim]This keeps working even when Groq/NVIDIA quota is exhausted.[/dim]",
            border_style="cyan",
        )
    )

    cmd = ["devloop", "ask", q]
    if files:
        cmd += ["-f", *files]

    t0 = time.time()
    console.print()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            console.print(line, end="", markup=False, highlight=False)
        proc.wait()
    except FileNotFoundError:
        console.print("[red]devloop not found. Install it: bash claude-automate/install.sh[/red]")
        return
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        proc.terminate()
        return
    elapsed = time.time() - t0
    console.print(f"\n[dim]devloop · {elapsed:.1f}s · browser bridge[/dim]\n")


@main.command()
def models() -> None:
    """Show available models and current routing."""
    from danphe.llm.nvidia import MODELS as nv

    console.print("\n[bold]NVIDIA NIM (free tier):[/bold]")
    for tier, mid in nv.items():
        console.print(f"  [cyan]{tier:12}[/cyan] {mid}")
    console.print()
    console.print("[bold]Fast path:[/bold]")
    console.print("  [cyan]groq         [/cyan] llama-3.3-70b (small convos)")
    console.print()

    backend, tier = router.pick([{"role": "user", "content": "hi"}])
    console.print(f"[bold]Active route:[/bold] [cyan]{router.describe(backend, tier)}[/cyan]")

    if not config.GROQ_API_KEY:
        console.print("[yellow]  ⚠  GROQ_API_KEY not set[/yellow]")
    if not config.NVIDIA_API_KEY:
        console.print("[yellow]  ⚠  NVIDIA_API_KEY not set[/yellow]")
    blocked = router.blocked()
    if blocked:
        console.print("[yellow]  ⚠  rate-limited this session:[/yellow] "
                      + ", ".join(f"{b}" for b in blocked))
    console.print()


@main.command()
@click.argument("platform", type=click.Choice(["instagram", "whatsapp"]))
@click.argument("target")
@click.option("--auto-reply", is_flag=True, help="Automatically generate and send replies")
@click.option("--personality", default="", help="Personality style for replies")
def social(platform: str, target: str, auto_reply: bool, personality: str) -> None:
    """Social media automation — read conversations and auto-reply."""
    import asyncio
    import sys
    from pathlib import Path

    # Import the social media module
    project_root = Path(__file__).parent.parent
    social_script = project_root / "instra-automate" / "social_media.py"
    
    if not social_script.exists():
        console.print("[red]Social media automation script not found.[/red]")
        return

    # Build arguments for the script
    args = [sys.executable, str(social_script), platform, target]
    if auto_reply:
        args.append("--auto-reply")
    if personality:
        args.extend(["--personality", personality])

    console.print(f"  [cyan]Launching social media automation for {platform} with {target}[/cyan]")
    if auto_reply:
        console.print("  [dim]Auto-reply enabled[/dim]")
    if personality:
        console.print(f"  [dim]Personality: {personality}[/dim]")
    console.print()

    # Run the script
    import subprocess
    result = subprocess.run(args, cwd=str(social_script.parent))
    if result.returncode != 0:
        console.print(f"[red]Command failed with exit code {result.returncode}[/red]")


if __name__ == "__main__":
    main()
