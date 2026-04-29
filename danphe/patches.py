"""
patches.py — extract FILE patches and bash commands from LLM responses.
Logic ported from claude-automate/devloop.py (already battle-tested).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_patches(response: str) -> list[tuple[str, str]]:
    """Return [(filepath, content), ...] from ```-fenced FILE blocks."""
    patches = []
    # backtick blocks with # FILE: header
    pattern = re.compile(r"```(?:\w+)?\n\s*#\s*FILE:\s*(.+?)\n(.*?)```", re.DOTALL)
    for m in pattern.finditer(response):
        patches.append((m.group(1).strip(), m.group(2)))
    if patches:
        return patches

    # fallback: bare "python\n# FILE: ..." blocks
    lines = response.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "python":
            i += 1
            if i < len(lines) and "# FILE:" in lines[i]:
                file_path = lines[i].replace("# FILE:", "").strip()
                i += 1
                content_lines = []
                while i < len(lines):
                    ls = lines[i].strip().lower()
                    if ls in ["bash", "python"] or ls.startswith("```"):
                        break
                    content_lines.append(lines[i])
                    i += 1
                while content_lines and not content_lines[-1].strip():
                    content_lines.pop()
                patches.append((file_path, "\n".join(content_lines)))
                continue
        i += 1
    return patches


def extract_bash(response: str) -> list[str]:
    """Return bash command blocks from the response."""
    cmds = []
    backticked = re.findall(r"```(?:bash|sh|shell)\n(.*?)```", response, re.DOTALL)
    if backticked:
        for block in backticked:
            current: list[str] = []
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped:
                    if current:
                        cmds.append("\n".join(current))
                        current = []
                    continue
                if stripped.startswith("#") and not current:
                    continue
                current.append(line)
            if current:
                cmds.append("\n".join(current))
        if cmds:
            return cmds

    # fallback: bare "bash\n<cmd>" blocks
    lines = response.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "bash":
            i += 1
            current = []
            while i < len(lines):
                ls = lines[i].strip().lower()
                if ls in ["bash", "python"] or ls.startswith("```"):
                    break
                if not lines[i].strip():
                    i += 1
                    continue
                current.append(lines[i])
                i += 1
            if current:
                cmds.append("\n".join(current))
            continue
        i += 1
    return [c for c in cmds if c.strip()]


# ── Apply ─────────────────────────────────────────────────────────────────────

class ApplyResult:
    def __init__(self):
        self.patched: list[str] = []
        self.commands: list[dict] = []   # [{cmd, rc, output}]
        self.success = True


def apply_patches(response: str, cwd: str) -> ApplyResult:
    """
    Apply FILE patches and bash commands extracted from response.
    Returns ApplyResult with details of what happened.
    """
    result = ApplyResult()
    patches  = extract_patches(response)
    commands = extract_bash(response)

    if not patches and not commands:
        result.success = False
        return result

    # Apply file patches
    for rel_path, content in patches:
        try:
            full = Path(rel_path) if rel_path.startswith("/") else Path(cwd) / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            if full.exists():
                bak = full.with_suffix(full.suffix + ".bak")
                shutil.copy2(full, bak)
            full.write_text(content, encoding="utf-8")
            result.patched.append(str(full))
        except Exception as e:
            result.success = False
            result.commands.append({"cmd": f"PATCH {rel_path}", "rc": 1, "output": str(e)})
            return result

    # Run bash commands
    for cmd in commands:
        try:
            r = subprocess.run(
                cmd, shell=True, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120,
            )
            out = (r.stdout + "\n" + r.stderr).strip()
            result.commands.append({"cmd": cmd, "rc": r.returncode, "output": out})
            if r.returncode != 0:
                result.success = False
                return result
        except subprocess.TimeoutExpired:
            result.success = False
            result.commands.append({"cmd": cmd, "rc": -1, "output": "timeout"})
            return result

    return result


# ── File collection (shared with agent) ──────────────────────────────────────

def collect_files(paths: list[str], skip_dirs: set, code_exts: set,
                  max_kb: int = 100, max_files: int = 30) -> list[Path]:
    collected: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        if path.is_file():
            collected.append(path)
        elif path.is_dir():
            found = []
            for f in sorted(path.rglob("*")):
                if not f.is_file():
                    continue
                if any(s in f.parts for s in skip_dirs):
                    continue
                if any(part.startswith(".") for part in f.parts):
                    continue
                if f.suffix not in code_exts and f.name not in code_exts:
                    continue
                if f.stat().st_size > max_kb * 1024:
                    continue
                found.append(f)
            collected.extend(found[:max_files])

    seen, result = set(), []
    for f in collected:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result
