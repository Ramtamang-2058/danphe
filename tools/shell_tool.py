"""
tools/shell_tool.py — run shell commands and capture output.
"""
from __future__ import annotations
import subprocess
from pathlib import Path


TIMEOUT = 120  # seconds


def run(cmd: str, cwd: str | Path | None = None) -> dict:
    """
    Run a shell command.
    Returns {"cmd": cmd, "rc": int, "stdout": str, "stderr": str, "output": str}
    """
    cwd = str(cwd or Path.cwd())
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=TIMEOUT,
        )
        output = (r.stdout + "\n" + r.stderr).strip()
        return {
            "cmd": cmd,
            "rc": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "output": output,
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "rc": -1, "stdout": "", "stderr": "timeout", "output": "timeout"}
    except Exception as e:
        return {"cmd": cmd, "rc": -1, "stdout": "", "stderr": str(e), "output": str(e)}


def run_many(cmds: list[str], cwd: str | Path | None = None) -> list[dict]:
    """Run multiple commands sequentially. Stops on first failure."""
    results = []
    for cmd in cmds:
        r = run(cmd, cwd=cwd)
        results.append(r)
        if r["rc"] != 0:
            break
    return results
