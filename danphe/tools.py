"""
tools.py — OpenAI-format tool schemas and Python executors.
"""
from __future__ import annotations
import glob as _glob_mod
import subprocess
from pathlib import Path
from typing import Any

from .config import MAX_FILE_KB, SKIP_DIRS

SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file and return its full contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates directories if needed, saves .bak backup).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination file path"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command and return stdout + stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command to run"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: current dir)"},
                    "pattern": {"type": "string", "description": "Optional glob pattern filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a text pattern in source files using grep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text or regex pattern to search"},
                    "path": {"type": "string", "description": "Directory to search in (default: current dir)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List all available skills with brief descriptions.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read the full content of a specific skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the skill to read"},
                },
                "required": ["name"],
            },
        },
    },
]


def execute(name: str, args: dict[str, Any]) -> str:
    """Dispatch a tool call by name, return string result."""
    try:
        if name == "read_file":
            return _read(args["path"])
        if name == "write_file":
            return _write(args["path"], args["content"])
        if name == "run_bash":
            return _bash(args["command"], int(args.get("timeout", 30)))
        if name == "list_files":
            return _ls(args.get("path", "."), args.get("pattern"))
        if name == "search_code":
            return _grep(args["pattern"], args.get("path", "."))
        if name == "list_skills":
            return _list_skills()
        if name == "read_skill":
            return _read_skill(args["name"])
        return f"Unknown tool: {name}"
    except KeyError as e:
        return f"Missing required argument {e} for tool {name}"
    except Exception as e:
        return f"Tool error ({name}): {e}"


def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: file not found: {path}"
    size_kb = p.stat().st_size / 1024
    if size_kb > MAX_FILE_KB:
        return f"Error: file too large ({size_kb:.0f}KB > {MAX_FILE_KB}KB limit)"
    return p.read_text(errors="replace")


def _write(path: str, content: str) -> str:
    try:
        p = Path(path)
        # Validate path
        if not path or path == "/":
            return f"Error: invalid path: {path}"

        # Create parent directories
        p.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if file exists
        if p.exists():
            try:
                bak = p.with_suffix(p.suffix + ".bak")
                bak.write_text(p.read_text(errors="replace"), encoding="utf-8")
            except Exception as e:
                return f"Error: failed to backup {path}: {e}"

        # Write the file with UTF-8 encoding
        p.write_text(content, encoding="utf-8")
        lines = content.count("\n") + 1
        size_kb = len(content.encode("utf-8")) / 1024
        return f"Written {path} ({lines} lines, {size_kb:.1f}KB)"
    except PermissionError:
        return f"Error: permission denied writing to {path}"
    except OSError as e:
        return f"Error: OS error writing to {path}: {e}"
    except Exception as e:
        return f"Error: failed to write {path}: {e}"


def _bash(command: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    parts = []
    if r.stdout.strip():
        parts.append(r.stdout.rstrip())
    if r.stderr.strip():
        parts.append(f"stderr: {r.stderr.rstrip()}")
    if r.returncode != 0:
        parts.append(f"exit code: {r.returncode}")
    return "\n".join(parts) if parts else "(no output)"


def _ls(path: str = ".", pattern: str | None = None) -> str:
    p = Path(path)
    if not p.exists():
        return f"Error: path not found: {path}"
    items = []
    try:
        for item in sorted(p.iterdir()):
            if item.name.startswith(".") or item.name in SKIP_DIRS:
                continue
            if pattern and not _glob_mod.fnmatch.fnmatch(item.name, pattern):
                continue
            items.append(item.name + ("/" if item.is_dir() else ""))
    except PermissionError:
        return f"Error: permission denied: {path}"
    return "\n".join(items) if items else "(empty)"


def _grep(pattern: str, path: str = ".") -> str:
    r = subprocess.run(
        [
            "grep", "-r", "-n",
            "--include=*.py", "--include=*.js", "--include=*.ts",
            "--include=*.go", "--include=*.rs", "--include=*.json",
            "--include=*.yaml", "--include=*.toml",
            "-m", "40", pattern, path,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    out = r.stdout.strip()
    if not out:
        return f"No matches for '{pattern}' in {path}"
    lines = out.split("\n")
    if len(lines) > 40:
        lines = lines[:40] + [f"… ({len(out.split(chr(10))) - 40} more lines truncated)"]
    return "\n".join(lines)


def _list_skills() -> str:
    from .config import load_skills
    skills = load_skills()
    if not skills:
        return "No skills available."

    lines = ["Available skills:"]
    for name, content in skills.items():
        # Get first line or first 100 chars as description
        first_line = content.split('\n', 1)[0].strip()
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."
        lines.append(f"- {name}: {first_line}")
    return "\n".join(lines)


def _read_skill(name: str) -> str:
    from .config import load_skills
    skills = load_skills()
    if name not in skills:
        return f"Error: skill '{name}' not found. Use list_skills to see available skills."
    return f"## {name}\n\n{skills[name]}"
