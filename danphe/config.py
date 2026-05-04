"""
config.py — load .env, CLAUDE.md, and ~/.danphe/skills/*.md
"""
import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# ── Load .env from cwd or home ────────────────────────────────────────────────
load_dotenv(find_dotenv(usecwd=True), override=False)
load_dotenv(Path.home() / ".danphe" / ".env", override=False)
# Fallback for local development if installed via pip -e:
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# ── API keys ──────────────────────────────────────────────────────────────────
NVIDIA_API_KEY  = os.getenv("NVIDIA_API_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
FORCE_MODEL     = os.getenv("DANPHE_MODEL", "")
MAX_TOKENS      = int(os.getenv("DANPHE_MAX_TOKENS", "16384"))
DEBUG           = os.getenv("DANPHE_DEBUG", "").lower() in ("1", "true", "yes")

# ── CLAUDE.md — project context injected into every prompt ───────────────────
def load_claude_md(cwd: Path | None = None) -> str:
    """
    Search for CLAUDE.md up the directory tree (same as Claude Code).
    Returns content or empty string.
    """
    search = cwd or Path.cwd()
    for directory in [search, *search.parents]:
        candidate = directory / "CLAUDE.md"
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    return ""

# ── Skill files — ~/.danphe/skills/*.md ──────────────────────────────────────
def load_skills() -> dict[str, str]:
    """
    Load all .md files from ~/.danphe/skills/.
    Returns {skill_name: content}.
    """
    skills_dir = Path.home() / ".danphe" / "skills"
    skills: dict[str, str] = {}
    if not skills_dir.exists():
        return skills
    for f in sorted(skills_dir.glob("*.md")):
        try:
            skills[f.stem] = f.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return skills

# ── Skip dirs for file collection (same as devloop) ──────────────────────────
SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache",
}

CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".cs", ".rb", ".sh", ".yaml", ".yml",
    ".toml", ".json", ".sql", ".md", ".txt", ".html", ".css",
    ".cfg", ".ini", ".env", "Dockerfile",
}

MAX_FILE_KB = 100
MAX_FILES   = 30
