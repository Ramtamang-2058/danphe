"""
tools/file_tool.py — read and write files for the agent.
"""
from __future__ import annotations
from pathlib import Path
from danphe.config import SKIP_DIRS, CODE_EXTS, MAX_FILE_KB, MAX_FILES


def read_file(path: str | Path) -> str:
    """Read a file and return its content with a header."""
    p = Path(path)
    if not p.exists():
        return f"[file not found: {path}]"
    if p.stat().st_size > MAX_FILE_KB * 1024:
        return f"[file too large (>{MAX_FILE_KB}KB): {path}]"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return f"# FILE: {p}\n{content}"
    except Exception as e:
        return f"[error reading {path}: {e}]"


def read_files(paths: list[str | Path]) -> str:
    """Read multiple files and concatenate with headers."""
    parts = []
    for p in paths:
        parts.append(read_file(p))
    return "\n\n".join(parts)


def collect_project_files(cwd: Path | None = None, max_files: int = MAX_FILES) -> list[Path]:
    """
    Collect code files from cwd (respects SKIP_DIRS and CODE_EXTS).
    Same logic as devloop.
    """
    root = cwd or Path.cwd()
    found = []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        if any(part.startswith(".") for part in f.parts if part != "."):
            continue
        if f.suffix not in CODE_EXTS and f.name not in CODE_EXTS:
            continue
        if f.stat().st_size > MAX_FILE_KB * 1024:
            continue
        found.append(f)
        if len(found) >= max_files:
            break
    return found


def project_tree(cwd: Path | None = None) -> str:
    """Return a compact file tree string for context."""
    root = cwd or Path.cwd()
    files = collect_project_files(root)
    lines = [f"Project root: {root}"]
    for f in files:
        try:
            lines.append(f"  {f.relative_to(root)}")
        except ValueError:
            lines.append(f"  {f}")
    return "\n".join(lines)
