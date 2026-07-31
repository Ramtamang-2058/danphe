"""
ui.py — Terminal UI: mist/thinking animation, tool panels, streaming helpers.
"""
from __future__ import annotations
import math
import time
from contextlib import contextmanager

from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console(highlight=False)

# ── Mist animation constants ───────────────────────────────────────────────────

# Density levels from sparse → dense (13 steps)
_MIST = " .·:∴░▒▓▒░∴:·"
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_MIST_W = 26


def _mist_row(t: float) -> list[tuple[str, str]]:
    """
    Generate one frame of mist: list of (char, style) tuples.
    Three sine waves at golden-ratio frequency multiples interfere to create
    a natural-looking wave pattern.
    """
    n = len(_MIST)
    result = []
    for i in range(_MIST_W):
        x = i / _MIST_W
        phi = x * math.tau - t * 2.4
        # Interference: base + φ-multiple harmonics
        v = (
            math.sin(phi) +
            math.sin(phi * 1.618 + t * 1.1) +
            math.sin(phi * 0.382 - t * 0.65)
        ) / 3.0                            # range ≈ -1 .. +1
        density = (v + 1.0) / 2.0         # 0 .. 1
        idx = int(density * (n - 1))
        char = _MIST[max(0, min(idx, n - 1))]

        if density > 0.78:
            style = "bold cyan"
        elif density > 0.52:
            style = "cyan"
        elif density > 0.28:
            style = "dim cyan"
        else:
            style = "dim blue"
        result.append((char, style))
    return result


class _Thinking:
    """
    Rich renderable: animated mist with spinner and elapsed time.
    Label can be updated live (e.g. "thinking" → "running tests").
    """

    def __init__(self, label: str = "thinking"):
        self.label = label
        self._t0 = time.time()

    def __rich__(self) -> Text:
        t = time.time() - self._t0
        spin = _SPIN[int(t * 13) % len(_SPIN)]

        # Label pulse: gently brightens on a ~2s cycle
        pulse = math.sin(t * math.pi * 0.8) * 0.5 + 0.5  # 0..1
        label_style = "bold cyan" if pulse > 0.7 else "cyan"

        out = Text()
        out.append(f"{spin} ", style="bold cyan")
        out.append(f"{self.label}  ", style=label_style)

        for char, style in _mist_row(t):
            out.append(char, style=style)

        out.append(f"  {t:.1f}s", style="dim")
        return out


# ── Public context manager ─────────────────────────────────────────────────────

@contextmanager
def thinking(label: str = "thinking", *, fps: int = 20):
    """
    Show the mist thinking animation while the body of the `with` block runs.
    The returned object has a mutable `.label` attribute you can update.

    Usage:
        with ui.thinking("loading") as indicator:
            result = slow_call()
            indicator.label = "processing"
            more_work()
    """
    display = _Thinking(label)
    with Live(display, refresh_per_second=fps, transient=True, console=console):
        yield display


# ── Tool call display ──────────────────────────────────────────────────────────

def show_tool(name: str, args: dict | None) -> None:
    """Print a tool-call line: '  → read_file(path="api.py")'"""
    args = args or {}
    args_str = ", ".join(
        f"[bold]{k}[/bold]=[dim]{repr(str(v))[:48]}[/dim]"
        for k, v in args.items()
    )
    console.print(f"  [dim]→[/dim] [cyan]{name}[/cyan]({args_str})")


def show_result(result: str, ok: bool = True) -> None:
    """Print a tool result line with ✓ or ✗."""
    icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
    first = result.split("\n")[0][:70].rstrip()
    suffix = f" [dim]… ({len(result)} chars)[/dim]" if len(result) > 120 else ""
    console.print(f"    {icon} [dim]{first}[/dim]{suffix}")


# ── Streaming helper ───────────────────────────────────────────────────────────

def stream_response(chunks) -> str:
    """
    Stream text chunks directly to console as they arrive.
    Returns the full accumulated string.
    """
    full = ""
    for chunk in chunks:
        console.print(chunk, end="", markup=False, highlight=False)
        full += chunk
    console.print()
    return full
