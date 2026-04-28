#!/usr/bin/env python3
"""
devloop — Agentic dev loop via Brave browser automation (no API key needed)

MODES:
  devloop run 'python app.py'               # run, auto-fix errors, retry
  devloop ask "what does this do"           # ask Claude, print answer to CLI
  devloop ask "review this" -f src/main.py  # ask + attach files
  devloop ask "fix this" -f ./src ./tests   # ask + attach whole dirs

AGENTIC BEHAVIOR:
  - ask:  Claude answers → printed to CLI → if fix needed, applied → done
  - run:  command runs → on error → Claude fixes → retry → loop until pass
"""

import argparse, datetime, logging, os, re, shutil, subprocess, sys, time
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
BRAVE_PATHS = [
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    "/opt/brave.com/brave/brave",
    # snap Brave is sandboxed and conflicts with Playwright — skip it
    # "/snap/bin/brave",
]
# snap Brave profile (copy login from here on first run, if it exists)
BRAVE_PROFILE   = Path.home() / "snap/brave/current/.config/BraveSoftware/Brave-Browser/Default"
# devloop uses Playwright Chromium with its own profile in plain home dir (no snap restrictions)
AUTO_PROFILE    = Path.home() / ".devloop-profile"
DEBUG_LOG       = Path.home() / ".devloop-debug.log"
DEBUG_HTML      = Path.home() / ".devloop-debug.html"
APP_LOG         = Path.home() / ".devloop.log"

# Configure logging
logger = logging.getLogger("devloop")
logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler(APP_LOG)
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_fh)
logger.propagate = False
NEW_CHAT_URL    = "https://claude.ai/new"
SESSION_FILE    = Path.home() / ".devloop-session"
SESSIONS_DIR    = Path.home() / ".devloop-sessions"
RESPONSE_TIMEOUT = 180   # seconds to wait for Claude
POLL_INTERVAL    = 1.0
STABLE_POLLS     = 3     # consecutive identical polls = done
MAX_RETRIES      = 3     # auto-fix retry limit for `run` mode

DIR_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".cs", ".rb", ".sh", ".yaml", ".yml", ".toml", ".json", ".sql",
    ".md", ".txt", ".html", ".css", ".cfg", ".ini", ".env", "Dockerfile",
}
MAX_FILE_KB = 100
MAX_FILES   = 30
SKIP_DIRS   = {
    "__pycache__", "node_modules", ".git", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache",
}
# ─────────────────────────────────────────────────────────────────────────────


# ── Browser helpers ───────────────────────────────────────────────────────────

def _log_debug_info(page, message: str):
    """Write debug state to local files for troubleshooting."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.debug(f"DEBUG_INFO: {message} | URL: {page.url}")
        
        with open(DEBUG_LOG, "a") as f:
            f.write(f"\n[{ts}] {message}\n")
            f.write(f"URL: {page.url}\n")
            
        html = page.content()
        with open(DEBUG_HTML, "w") as f:
            f.write(html)
        
        print(f"\n[devloop] 📝 Debug log saved to {DEBUG_LOG}")
        print(f"[devloop] 📝 Page HTML saved to {DEBUG_HTML}")
    except Exception as e:
        logger.error(f"Failed to write debug info: {e}")
        print(f"[devloop] ⚠  Failed to write debug info: {e}")


def find_brave():
    for p in BRAVE_PATHS:
        if Path(p).exists():
            return p
    for name in ["brave-browser", "brave"]:
        r = subprocess.run(["which", name], capture_output=True, text=True)
        if r.returncode == 0:
            path = r.stdout.strip()
            if "/snap/" not in path:  # snap Brave is sandboxed, skip it
                return path
    return None


def ensure_profile():
    for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lp = AUTO_PROFILE / lock
        try:
            if lp.exists() or lp.is_symlink():
                lp.unlink()
        except Exception:
            pass

    if AUTO_PROFILE.exists():
        try:
            subprocess.run(["chmod", "-R", "u+rwX", str(AUTO_PROFILE)],
                           capture_output=True, check=False)
        except Exception:
            pass
        return

    if BRAVE_PROFILE.exists():
        print("[devloop] First run: copying Brave profile (keeps your Claude login)…")
        shutil.copytree(
            str(BRAVE_PROFILE), str(AUTO_PROFILE), symlinks=False,
            ignore=shutil.ignore_patterns(
                "SingletonLock", "SingletonSocket", "SingletonCookie",
                "*.log", "*.ldb", "*.tmp",
            ),
        )
        subprocess.run(["chmod", "-R", "u+rwX", str(AUTO_PROFILE)],
                       capture_output=True, check=False)
        print(f"[devloop] Profile ready at {AUTO_PROFILE}")
    else:
        AUTO_PROFILE.mkdir(parents=True, exist_ok=True)
        print(f"[devloop] ⚠  Brave profile not found at {BRAVE_PROFILE}")
        print("  You'll be asked to log into Claude on first run.")


def get_browser(playwright, headless=False):
    ensure_profile()
    brave = find_brave()
    kwargs = dict(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-sync",
        ],
        user_data_dir=str(AUTO_PROFILE),
    )
    if brave:
        kwargs["executable_path"] = brave
        print(f"[devloop] Brave: {brave}")
    else:
        print("[devloop] Brave not found → using Playwright Chromium")
    return playwright.chromium.launch_persistent_context(**kwargs)


# ── Claude page interaction ───────────────────────────────────────────────────

INPUT_SELECTORS = [
    'textarea[placeholder*="message" i]',
    'textarea[placeholder*="ask" i]',
    'div[contenteditable="true"][data-placeholder]',
    'div[contenteditable="true"]',
    'textarea',
]

RESPONSE_SELECTORS = [
    '.font-claude-response',
    '[data-message-role="assistant"]',
    '[data-message-author-role="assistant"]',
    '[data-testid="assistant-message"]',
    '.font-claude-message',
    'div[class*="AssistantMessage"]',
    'div[class*="assistant-message"]',
    'article:has(span:text-is("Claude"))',  # Brute force Claude article
    'div.flex-1.gap-3:has(svg[aria-label="Claude"])',
    'div.grid.grid-cols-1.gap-2:has(div.prose)', # Fallback but constrained
]


def _is_assistant_element(el) -> bool:
    """Strictly verify if an element belongs to the assistant."""
    try:
        # 1. Check data attributes first
        role = el.get_attribute("data-message-role") or el.get_attribute("data-message-author-role")
        if role:
            return role == "assistant"
        
        # 2. Check for assistant-specific classes or test IDs
        testid = el.get_attribute("data-testid")
        if testid and "assistant" in testid.lower():
            return True
            
        # 3. Check class names
        cls = el.get_attribute("class") or ""
        if "AssistantMessage" in cls or "assistant-message" in cls or "font-claude-response" in cls:
            return True
            
        # 4. Check for Claude's icon/name inside
        if el.query_selector('svg[aria-label="Claude"]') or "Claude" in (el.inner_text()[:50] or ""):
            return True
            
    except Exception:
        pass
    return False


def _find_input(page, timeout_s=25):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for sel in INPUT_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    logger.debug(f"Input selector matched: {sel}")
                    return el
            except Exception:
                pass
        time.sleep(0.5)
    logger.error(f"Could not locate Claude input box after {timeout_s} s")
    raise RuntimeError(f"Could not locate Claude input box after {timeout_s} s")


def wait_for_page_ready(page, timeout_s=30):
    """Wait until the input box is visible — means page is interactive."""
    _find_input(page, timeout_s)


def _attach_files(page, files):
    logger.debug(f"Attempting to attach {len(files)} files")
    fi = page.query_selector('input[type="file"]')
    if fi:
        try:
            fi.set_input_files([str(f) for f in files])
            time.sleep(2)
            logger.debug("Files attached via input[type=file]")
            return
        except Exception as e:
            logger.error(f"Error attaching via input[type=file]: {e}")
            pass

    attach_sels = [
        'button[aria-label*="ttach" i]',
        'button[aria-label*="file" i]',
        '[data-testid*="attach"]',
        'button[title*="ttach" i]',
        'label[for*="file" i]',
    ]
    for sel in attach_sels:
        try:
            btn = page.query_selector(sel)
            if btn:
                logger.debug(f"Clicking attachment button: {sel}")
                with page.expect_file_chooser(timeout=5000) as fc:
                    btn.click()
                fc.value.set_files([str(f) for f in files])
                time.sleep(2)
                logger.debug("Files attached via file chooser")
                return
        except Exception as e:
            logger.debug(f"Failed to attach via {sel}: {e}")
            continue

    logger.warning("All attachment methods failed")
    print("[devloop] ⚠  Could not attach files — sending text only")


def send_message(page, message: str, files: list = None):
    """Type and send a message, optionally attaching files first."""
    if files:
        logger.info(f"Attaching {len(files)} files")
        print(f"[devloop] 📎 Attaching {len(files)} file(s)…")
        _attach_files(page, files)

    for attempt in range(3):
        try:
            box = _find_input(page, timeout_s=10)
            box.click()
            time.sleep(0.3)
            box.press("Control+a")
            box.press("Delete")
            time.sleep(0.2)

            # Use JS to set content atomically — avoids type() race condition
            logger.debug("Setting message content via JS")
            page.evaluate("""(msg) => {
                const el = document.activeElement;
                
                // Try to use execCommand for better integration with React/complex frameworks
                try {
                    if (document.queryCommandSupported('insertText')) {
                        document.execCommand('insertText', false, msg);
                        return;
                    }
                } catch (e) {}

                if (el.tagName === 'TEXTAREA') {
                    el.value = msg;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    el.innerText = msg;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    // Move cursor to end
                    const range = document.createRange();
                    const sel = window.getSelection();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                }
            }""", message)
            time.sleep(0.5)

            # Verify content is actually there before sending
            actual = box.inner_text() or box.input_value() if box.get_attribute("tagName") == "TEXTAREA" else box.inner_text()
            if not actual or len(actual.strip()) < 3:
                # Fallback: type slowly
                logger.warning("JS paste empty, falling back to type()")
                print(f"[devloop] ⚠  JS paste empty, falling back to type()…")
                box.click()
                box.press("Control+a")
                box.type(message, delay=15)
                time.sleep(0.5)

            box.press("Enter")
            logger.info("Message sent successfully")
            print("[devloop] ✉  Sent")
            return
        except Exception as e:
            if attempt < 2:
                logger.warning(f"Send attempt {attempt + 1} failed: {e}")
                print(f"[devloop] ⚠  Send attempt {attempt + 1} failed, retrying…")
                time.sleep(1.5)
            else:
                logger.error(f"Failed to send after 3 attempts: {e}")
                raise RuntimeError(f"Failed to send after 3 attempts: {e}")


def _count_assistant_messages(page) -> int:
    """Count how many assistant message elements exist right now."""
    count = 0
    for sel in RESPONSE_SELECTORS:
        try:
            els = page.query_selector_all(sel)
            for el in els:
                if _is_assistant_element(el):
                    count += 1
            if count > 0:
                return count
        except Exception:
            pass
    return 0


def wait_for_response(page) -> str:
    """
    Poll until Claude's NEW assistant message stops changing.
    Anchors to message count BEFORE send so we never read a stale reply.
    """
    baseline = _count_assistant_messages(page)
    return wait_for_response_with_baseline(page, baseline)


def _get_new_assistant_text(page, baseline: int = 0) -> str:
    """Return text of the latest assistant message, only if it's a NEW one (after baseline)."""
    for sel in RESPONSE_SELECTORS:
        try:
            els = [el for el in page.query_selector_all(sel) if _is_assistant_element(el)]
            if els and len(els) > baseline:
                el = els[-1]
                
                # Check for "thinking" or "processing" state indicators
                try:
                    # Claude sometimes shows intermediate "Working", "Searching", "Thinking" in bubbles.
                    content_els = el.query_selector_all('.prose, [data-testid="message-content-container"]')
                    if content_els:
                        text = "\n\n".join([c.inner_text() for c in content_els])
                    else:
                        text = el.inner_text() or el.text_content() or ""

                    # If it's still generating or thinking, we might see pulse or specific labels
                    is_thinking = False
                    if el.query_selector('.animate-pulse'):
                        is_thinking = True
                    
                    # More robust status check: if most lines are just status words
                    lines = [l.strip().lower().rstrip('.').rstrip('…') for l in text.splitlines() if l.strip()]
                    status_words = {
                        "working", "searching", "thinking", "script", "find", 
                        "analyzing", "processing", "search for project directories",
                        "find integrated-dastaa project", "search for integrated-dastaa project"
                    }
                    
                    # If the response is very short and contains mostly status words, it's likely thinking
                    if not is_thinking and lines:
                        # Check if all lines look like status/progress markers
                        all_status = True
                        for line in lines:
                            # If a line is more than 6 words, it's probably real content
                            if len(line.split()) > 6:
                                all_status = False
                                break
                            # If the line doesn't contain any status keywords
                            if not any(sw in line for sw in status_words):
                                all_status = False
                                break
                        
                        if all_status:
                            is_thinking = True

                    if is_thinking:
                        logger.debug(f"Message is still in 'thinking' state. Text snippet: {text[:50].replace(chr(10), ' ')}...")
                        return ""
                except: pass
                
                if text.strip():
                    # If it starts with "Claude", it might be the header, try to skip it if it's just the label
                    lines = text.splitlines()
                    if lines and lines[0].strip() == "Claude" and len(lines) > 1:
                        text = "\n".join(lines[1:])
                    return text
        except Exception as e:
            logger.error(f"Error querying selector {sel}: {e}")
            pass
    return ""


# ── File collection ───────────────────────────────────────────────────────────

def collect_files(paths: list) -> list:
    collected = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"[devloop] ⚠  Not found: {p}")
            continue
        if path.is_file():
            collected.append(path)
        elif path.is_dir():
            found = []
            for f in sorted(path.rglob("*")):
                if not f.is_file():
                    continue
                if any(skip in f.parts for skip in SKIP_DIRS):
                    continue
                if any(part.startswith(".") for part in f.parts):
                    continue
                if f.suffix not in DIR_EXTS and f.name not in DIR_EXTS:
                    continue
                if f.stat().st_size > MAX_FILE_KB * 1024:
                    continue
                found.append(f)
            if len(found) > MAX_FILES:
                print(f"[devloop]   {p}: {len(found)} files, using first {MAX_FILES}")
                found = found[:MAX_FILES]
            else:
                print(f"[devloop]   {p}: {len(found)} files")
            collected.extend(found)

    seen, result = set(), []
    for f in collected:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


# ── Fix extraction + apply ────────────────────────────────────────────────────

def extract_patches(response: str) -> list[tuple[str, str]]:
    patches = []
    # 1. Try backticked blocks (the most reliable)
    pattern_bt = re.compile(r"```(?:\w+)?\n\s*#\s*FILE:\s*(.+?)\n(.*?)```", re.DOTALL)
    for m in pattern_bt.finditer(response):
        patches.append((m.group(1).strip(), m.group(2)))
    if patches:
        return patches

    # 2. Try non-backticked blocks as per user prompt: "python\n# FILE: ..."
    lines = response.splitlines()
    i = 0
    while i < len(lines):
        line_strip = lines[i].strip().lower()
        if line_strip == "python":
            i += 1
            if i < len(lines) and "# FILE:" in lines[i]:
                file_path = lines[i].replace("# FILE:", "").strip()
                i += 1
                content_lines = []
                while i < len(lines):
                    ls = lines[i].strip().lower()
                    if ls in ["bash", "python"] or ls.startswith("```"):
                        break
                    if not lines[i].strip():
                        if i + 1 < len(lines):
                            next_ls = lines[i+1].strip().lower()
                            if next_ls in ["bash", "python"] or next_ls.startswith("```"):
                                break
                            if lines[i+1].strip() and not (lines[i+1].startswith(" ") or lines[i+1].startswith("\t")):
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
    cmds = []
    # 1. Try backticked blocks
    backticked = re.findall(r"```(?:bash|sh|shell)\n(.*?)```", response, re.DOTALL)
    if backticked:
        for block in backticked:
            current_cmd = []
            for line in block.splitlines():
                stripped = line.strip()
                if not stripped:
                    if current_cmd:
                        cmds.append("\n".join(current_cmd))
                        current_cmd = []
                    continue
                if stripped.startswith("#") and not current_cmd:
                    continue
                current_cmd.append(line)
            if current_cmd:
                cmds.append("\n".join(current_cmd))
        if cmds:
            return cmds

    # 2. Try non-backticked blocks: "bash\n<commands>"
    lines = response.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().lower() == "bash":
            i += 1
            current_cmd = []
            while i < len(lines):
                ls = lines[i].strip().lower()
                if ls in ["bash", "python"] or ls.startswith("```"):
                    break
                if not lines[i].strip():
                    if current_cmd:
                        if i + 1 < len(lines) and lines[i+1].strip() and lines[i+1].strip().lower() not in ["bash", "python"]:
                            break
                    i += 1
                    continue
                current_cmd.append(lines[i])
                i += 1
            if current_cmd:
                cmds.append("\n".join(current_cmd))
            continue
        i += 1
    return [c for c in cmds if c.strip()]


def apply_fix(response: str, cwd: str) -> bool:
    patches  = extract_patches(response)
    commands = extract_bash(response)

    if not patches and not commands:
        print("[devloop] ℹ  No actionable code blocks found")
        return False

    print(f"[devloop] 🔧 Applying {len(patches)} patch(es) + {len(commands)} command(s)…")

    results = []
    for rel_path, content in patches:
        try:
            full = Path(rel_path) if rel_path.startswith("/") else Path(cwd) / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            if full.exists():
                bak = full.with_suffix(full.suffix + ".bak")
                shutil.copy2(full, bak)
                print(f"[devloop]   📦 Backup → {bak.name}")
            full.write_text(content)
            rel = full.relative_to(cwd) if full.is_relative_to(cwd) else full
            print(f"[devloop]   ✓ Patched {rel}")
        except Exception as e:
            print(f"[devloop]   ✗ Patch {rel_path}: {e}")
            return False

    for cmd in commands:
        print(f"[devloop]   ▶ {cmd}")
        try:
            r = subprocess.run(
                cmd, shell=True, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120,
            )
            if r.stdout:
                print(r.stdout.rstrip())
            if r.stderr and r.returncode != 0:
                print(r.stderr.rstrip(), file=sys.stderr)
            status = "✓" if r.returncode == 0 else "✗"
            print(f"[devloop]   {status} rc={r.returncode}")
            
            # Store results for feedback
            out = (r.stdout + "\n" + r.stderr).strip()
            results.append(f"Command: {cmd}\nExit Code: {r.returncode}\nOutput:\n{out}")

            if r.returncode != 0:
                # If a command fails, we still want to return the feedback if possible
                # but for simplicity we'll just stop here
                apply_fix.last_results = results
                return False
        except subprocess.TimeoutExpired:
            print("[devloop]   ✗ Command timed out", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[devloop]   ✗ {e}", file=sys.stderr)
            return False

    apply_fix.last_results = results
    print("[devloop] ✅ All fixes applied")
    return True

apply_fix.last_results = []


# ── Prompt builders ───────────────────────────────────────────────────────────

_CODE_INSTRUCTIONS = """\
You are an AI developer agent with local terminal access.
If you want to run a command or fix something, you MUST use one of these blocks:

bash
<commands to run>

python
# FILE: path/to/file.py
<complete file content>

IMPORTANT: 
- I only execute what is inside these blocks. 
- If you just talk, I will assume there is nothing more to do and I will stop.
- If the user asks you to "find", "give", "locate" something, you MUST use a bash block with 'find', 'ls', or 'grep' to search for it. Do NOT just say you are doing it or use placeholder text like "Working".
- ALWAYS provide the actual shell command to perform the search or action.
- Your goal is to provide executable actions. If you don't provide a block, the loop ends.
- When the task is truly complete, include the word "DONE"."""


def build_ask_prompt(question: str, file_list: str = "") -> str:
    parts = [_CODE_INSTRUCTIONS, ""]
    if file_list:
        parts.append(f"Files attached:\n{file_list}\n")
    parts.append(question)
    return "\n".join(parts)


def build_error_prompt(cmd: str, stdout: str, stderr: str, cwd: str, fix_results: list = None) -> str:
    # Collect relevant project files, excluding junk
    py_files = []
    for f in Path(cwd).rglob("*"):
        if f.is_file() and f.suffix in {".py", ".js", ".ts", ".sh"}:
            if not any(s in f.parts for s in SKIP_DIRS):
                py_files.append(str(f.relative_to(cwd)))
    py_files = py_files[:15]

    output = (stdout + "\n" + stderr).strip()[-3000:]
    
    prompt = f"""\
{_CODE_INSTRUCTIONS}

Command that failed:
```
{cmd}
```

Output / error:
```
{output}
```
"""
    if fix_results:
        prompt += "\nResults of previous fixes you suggested:\n"
        for res in fix_results:
            prompt += f"```\n{res}\n```\n"

    prompt += f"\nProject files: {', '.join(py_files)}\n\nFix the error above."
    return prompt


# ── CLI output helper ─────────────────────────────────────────────────────────

def print_response(response: str, label: str = "CLAUDE"):
    if not response:
        return
    
    # Simple, clean separator
    print(f"\n--- {label} " + "-" * (60 - len(label)))
    
    # Print the response with a slight indentation for readability
    for line in response.splitlines():
        print(f"  {line}")
    
    print("-" * 65 + "\n")


# ── MODES ─────────────────────────────────────────────────────────────────────

def get_last_session(use_ppid=False):
    if use_ppid:
        ppid = os.getppid()
        pfile = SESSIONS_DIR / str(ppid)
        if pfile.exists():
            try:
                return pfile.read_text().strip()
            except Exception:
                pass
    
    if SESSION_FILE.exists():
        try:
            return SESSION_FILE.read_text().strip()
        except Exception:
            pass
    return None

def save_session(url: str, use_ppid=False):
    try:
        if "claude.ai/chat/" in url:
            SESSION_FILE.write_text(url)
            if use_ppid:
                SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
                (SESSIONS_DIR / str(os.getppid())).write_text(url)
    except Exception:
        pass

def mode_ask(args):
    from playwright.sync_api import sync_playwright

    question  = " ".join(args.question)
    files     = collect_files(args.files) if args.files else []
    file_list = "\n".join(f"  • {f}" for f in files)
    
    logger.info(f"Starting 'ask' mode. question='{question[:50]}...', files={len(files)}")

    if files:
        print(f"\n[devloop] 📎 {len(files)} file(s) to attach:")
        print(file_list)

    prompt = build_ask_prompt(question, file_list)

    with sync_playwright() as pw:
        try:
            ctx  = get_browser(pw)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            
            url = NEW_CHAT_URL
            if args.resume_url:
                url = args.resume_url
            elif args.resume:
                # Try PPID first, then global
                url = get_last_session(use_ppid=True) or get_last_session(use_ppid=False) or NEW_CHAT_URL
                if url == NEW_CHAT_URL:
                    print("[devloop] ℹ  No previous session found, starting new chat.")
            elif args.new:
                url = NEW_CHAT_URL
            else:
                # DEFAULT: Start new chat, but inform if a session could be resumed
                url = NEW_CHAT_URL
                last_session = get_last_session(use_ppid=True) or get_last_session(use_ppid=False)
                if last_session:
                    print(f"[devloop] ℹ  Starting new chat. To resume last session, use --resume")

            print(f"[devloop] 🔗 Loading {url}…")
            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)

            wait_for_page_ready(page)
            save_session(page.url, use_ppid=True)

            # Snapshot BEFORE send so wait_for_response ignores any existing messages
            baseline = _count_assistant_messages(page)

            # Wait a tiny bit to ensure the baseline is stable
            time.sleep(0.5)

            print(f"[devloop] ❓ {question}")
            send_message(page, prompt, files)
            response = wait_for_response_with_baseline(page, baseline)

            if not response:
                print("[devloop] ⚠  Got empty response — browser left open for manual review")
                print(f"[devloop] URL: {page.url}")
                _block_until_ctrl_c()
                ctx.close()
                return

            print_response(response)
            # Save final session URL
            save_session(page.url, use_ppid=True)

            patches  = extract_patches(response)
            commands = extract_bash(response)
            cwd      = os.getcwd()

            if patches or commands:
                print(f"[devloop] 🤖 Found {len(patches)} patch(es) + {len(commands)} command(s)")
                ans = input("[devloop] Apply them? [Y/n] ").strip().lower()
                if ans in ("", "y", "yes"):
                    apply_fix(response, cwd)
                else:
                    print("[devloop] Skipped.")
            else:
                print("[devloop] ℹ  No actionable code blocks — nothing to apply")

            print(f"[devloop] 🔗 Chat: {page.url}")
            ctx.close()
        except KeyboardInterrupt:
            print("\n[devloop] 🛑 Interrupted by user")
            sys.exit(130)
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                # This often happens during Ctrl+C in Playwright
                print("\n[devloop] 🛑 Browser closed unexpectedly")
            else:
                logger.exception("Error in mode_ask")
                print(f"[devloop] ❌ Error: {e}")
            sys.exit(1)


def wait_for_response_with_baseline(page, baseline: int) -> str:
    """Like wait_for_response but uses a pre-captured baseline."""
    logger.info(f"Waiting for response. baseline={baseline}")
    print("[devloop] ⏳ Waiting for Claude", end="", flush=True)
    start      = time.time()
    last_text  = ""
    stable_cnt = 0
    wait_for_response_with_baseline._logged_60s = False

    while time.time() - start < RESPONSE_TIMEOUT:
        # Re-check baseline if we are getting nothing
        text = _get_new_assistant_text(page, baseline)

        if not text and time.time() - start > 10:
             # Emergency fallback: if baseline seems wrong (e.g. page refreshed)
             # try to get the absolute last message if it looks like Claude's
             text = _get_new_assistant_text(page, baseline - 1 if baseline > 0 else 0)
             if text:
                 logger.debug("Baseline adjusted (-1)")
                 print("(adj)", end="", flush=True)

        if not text and time.time() - start > 30:
             # Last resort: just get the last message regardless of baseline
             # if it's been 30s and we have NOTHING.
             text = _get_new_assistant_text(page, 0)
             if text:
                 logger.debug("Emergency fallback to baseline 0")
                 print("(fallback)", end="", flush=True)

        if not text and time.time() - start > 60:
             # If we still have NOTHING after 60s, something is very wrong
             # Only log this ONCE to avoid spamming the log
             if not getattr(wait_for_response_with_baseline, "_logged_60s", False):
                 logger.warning(f"No response detected after 60s. Baseline={baseline}")
                 _log_debug_info(page, f"No response detected after 60s. Baseline={baseline}")
                 wait_for_response_with_baseline._logged_60s = True

        if text:
            # Check if Claude's action buttons (Copy, Retry, etc.) appeared — sign it's done
            is_finished = False
            try:
                # 1. Action buttons on the message itself
                finish_sels = [
                    'button[aria-label*="opy" i]', 
                    '.flex.items-center.justify-end.gap-2',
                    'svg[aria-label*="opy" i]',
                    'button[aria-label*="Share" i]',
                    'button[aria-label*="Helpful" i]',
                    'button[aria-label*="downvote" i]',
                    'button[aria-label*="retry" i]',
                    '[data-testid="message-actions"]',
                ]
                for s in finish_sels:
                    actions = page.query_selector(s)
                    if actions and actions.is_visible():
                        is_finished = True
                        logger.debug(f"Finish selector matched: {s}")
                        break
                
                # 2. Input box interactive + NO "Stop" button anywhere
                if not is_finished:
                    # Find stop button (usually one per page during generation)
                    stop_btn = page.query_selector('button[aria-label*="Stop" i], button svg circle[fill="currentColor"], button[aria-label="Stop Generating"]')
                    if not stop_btn:
                        # Double check if input box is ready
                        try:
                            box = _find_input(page, timeout_s=0.5)
                            if box and box.is_visible() and box.is_enabled():
                                # Heuristic: if input box is visible, enabled and NO stop button, likely done
                                if len(text) > 10 or stable_cnt > 0:
                                    is_finished = True
                                    logger.debug("Input box ready and no stop button; assuming finished.")
                        except: pass
            except Exception as e:
                logger.error(f"Error in finish detection: {e}")

            if text == last_text:
                stable_cnt += 1
                logger.debug(f"Stable poll {stable_cnt}/{STABLE_POLLS}. is_finished={is_finished}")
                print(".", end="", flush=True)
                
                # If stable but text looks like it might still be a status update, don't finish
                is_status = False
                lower_text = text.lower()
                status_patterns = [
                    "working...", "searching...", "thinking...", "script...", "analyzing...",
                    "search for", "find integrated", "processing..."
                ]
                if any(p in lower_text for p in status_patterns):
                    # If it's short and contains status patterns, it's likely just a progress marker
                    if len(text) < 200: 
                        is_status = True
                
                if (is_finished or stable_cnt >= STABLE_POLLS) and not is_status:
                    logger.info(f"Response complete. length={len(text)}")
                    print(" ✓")
                    return text.strip()
            else:
                logger.debug(f"Text updated. new length={len(text)}")
                last_text  = text
                stable_cnt = 0
                print("·", end="", flush=True)
        else:
            print("◌", end="", flush=True)

        time.sleep(POLL_INTERVAL)

    logger.error(f"Timeout waiting for response. last_text_len={len(last_text)}")
    print(" (timeout)")
    _log_debug_info(page, f"Timeout after {RESPONSE_TIMEOUT}s. Last text length: {len(last_text)}")
    return last_text.strip()


def wait_for_response(page) -> str:
    """Captures baseline internally (legacy wrapper)."""
    baseline = _count_assistant_messages(page)
    return wait_for_response_with_baseline(page, baseline)


def is_likely_question(cmd: str) -> bool:
    """Heuristic to determine if a string is a natural language question/request."""
    words = cmd.split()
    if not words:
        return False
    
    # If it's very long and has spaces, it's likely a sentence
    if len(words) > 6:
        return True
    
    # Common conversational starters
    starters = {"can", "how", "what", "where", "why", "who", "please", "give", "find", "show", "tell", "search"}
    if words[0].lower() in starters:
        # If it's a starter but also a valid command, check if it's used like a command
        # e.g., "find . -name ..." vs "find my project"
        if shutil.which(words[0]):
            # If it's 'find' or 'show' (often aliases), and has no flags (starting with -), it might be a question
            if not any(w.startswith("-") for w in words):
                return True
        else:
            return True
            
    # If the first word is not a command, it's likely a question
    if not shutil.which(words[0]):
        return True
        
    return False


def mode_run(args):
    from playwright.sync_api import sync_playwright

    cmd = " ".join(args.command)
    cwd = os.getcwd()
    
    logger.info(f"Starting 'run' mode. command='{cmd}'")

    fix_results = []
    max_attempts = 1 if args.once else MAX_RETRIES
    
    for attempt in range(1, max_attempts + 1):
        # Heuristic: if command looks like a question, skip execution and ask Claude directly
        is_question = is_likely_question(cmd)
        
        if is_question and attempt == 1:
            print(f"\n[devloop] ▶  {cmd}  (detected as question)")
            print(f"[devloop] 💡 Tip: Using 'devloop ask' is faster for questions.")
            print(f"[devloop]    Asking Claude to process this request…\n")
            r = None # Signal that we didn't run the command
        else:
            print(f"\n[devloop] ▶  {cmd}  (attempt {attempt}/{max_attempts})")
            r = subprocess.run(
                cmd, shell=True, cwd=cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if r.stdout:
                print(r.stdout)
            if r.stderr:
                print(r.stderr, file=sys.stderr)

            if r.returncode == 0:
                logger.info(f"Command succeeded on attempt {attempt}")
                print("\n[devloop] ✅ Success!")
                return
            
            logger.warning(f"Command failed with exit code {r.returncode}")
            print(f"\n[devloop] ✗ Failed (rc={r.returncode}) — asking Claude to fix…\n")

        prompt = build_error_prompt(cmd, r.stdout if r else "", r.stderr if r else "Detected as natural language question", cwd, fix_results=fix_results)

        with sync_playwright() as pw:
            try:
                ctx  = get_browser(pw)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                
                url = NEW_CHAT_URL
                if args.resume:
                    url = get_last_session(use_ppid=True) or get_last_session(use_ppid=False) or NEW_CHAT_URL
                    if url == NEW_CHAT_URL:
                        print("[devloop] ℹ  No previous session found, starting new chat.")
                elif args.new:
                    url = NEW_CHAT_URL
                else:
                    # DEFAULT: Start new chat, but inform if a session could be resumed
                    url = NEW_CHAT_URL
                    last_session = get_last_session(use_ppid=True) or get_last_session(use_ppid=False)
                    if last_session:
                        print(f"[devloop] ℹ  Starting new chat. To resume last session, use --resume")

                page.goto(url, wait_until="networkidle", timeout=30_000)
                wait_for_page_ready(page)
                save_session(page.url, use_ppid=True)
                
                baseline = _count_assistant_messages(page)
                time.sleep(0.5)
                send_message(page, prompt)
                response = wait_for_response_with_baseline(page, baseline)
                save_session(page.url, use_ppid=True)
                ctx.close()
            except KeyboardInterrupt:
                print("\n[devloop] 🛑 Interrupted by user")
                sys.exit(130)
            except Exception as e:
                if "Target page, context or browser has been closed" in str(e):
                    print("\n[devloop] 🛑 Browser closed unexpectedly")
                    response = None
                else:
                    logger.exception("Error in mode_run loop")
                    print(f"[devloop] ❌ Error: {e}")
                    response = None

        if not response:
            print("[devloop] ⚠  No response from Claude")
            break

        print_response(response, label="CLAUDE'S FIX")

        # Check for termination keyword "DONE" or "Nothing to fix"
        is_done = "DONE" in response.upper() or "NOTHING TO FIX" in response
        if is_done and not (extract_patches(response) or extract_bash(response)):
            print("[devloop] ℹ  Claude signaled completion — stopping loop.")
            return

        if apply_fix(response, cwd):
            # If all commands succeeded, check if we should stop
            is_question = is_likely_question(cmd)
            if is_question:
                print("[devloop] ℹ  Fix applied successfully and input looks like a question.")
                print("[devloop]    Assuming intent fulfilled — stopping loop.")
                return
        else:
            if not getattr(apply_fix, "last_results", None):
                # If no blocks were found AT ALL, Claude probably doesn't have a fix
                # or thinks it's done. No point in retrying.
                is_question = is_likely_question(cmd)
                if is_question:
                    print("[devloop] ℹ  Claude gave an answer but no executable commands.")
                    print("[devloop]    If you wanted an action, try rephrasing or use 'devloop ask'.")
                else:
                    print("[devloop] ℹ  Claude suggested no changes — stopping loop.")
                return
            else:
                # Some commands failed. Check if ANY command succeeded.
                # If the user asked "find out X", and Claude did "find ...",
                # that command likely succeeded and gave the answer in output.
                # In that case, we should probably stop because we "solved" the user's intent
                # even if the original (natural language) command still "fails" in the next loop.
                any_success = any(res.split("Exit Code: ")[1].split("\n")[0].strip() == "0" 
                                 for res in getattr(apply_fix, "last_results", []) if "Exit Code: " in res)
                
                if any_success and len(cmd.split()) > 4 and not shutil.which(cmd.split()[0]):
                    print("[devloop] ℹ  Some commands succeeded and input looks like a question.")
                    print("[devloop]    Assuming intent fulfilled — stopping loop.")
                    return

                print("[devloop] ⚠  Some fix commands failed, but continuing with feedback…")
        
        fix_results.extend(getattr(apply_fix, "last_results", []))
        # Keep only recent fix results to stay under token limits
        if len(fix_results) > 5:
            fix_results = fix_results[-5:]

    print(f"\n[devloop] ✗ Still failing after {max_attempts} attempts")
    sys.exit(1)


# ── Utility ───────────────────────────────────────────────────────────────────

def _block_until_ctrl_c():
    print("[devloop] Press Ctrl+C to close browser and exit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="devloop",
        description="Agentic dev loop via Brave browser — no API key needed",
    )
    sub = ap.add_subparsers(dest="mode", required=True)

    pr = sub.add_parser("run", help="Run command; auto-fix errors with Claude")
    pr.add_argument("command", nargs="+")
    pr.add_argument("--new", action="store_true", help="Start a new chat (default)")
    pr.add_argument("--resume", action="store_true", help="Resume the last conversation")
    pr.add_argument("--once", action="store_true", help="Run only once, no loop")

    pa = sub.add_parser("ask", help="Ask Claude; print answer to CLI")
    pa.add_argument("question", nargs="+")
    pa.add_argument("-f", "--files", nargs="+", metavar="PATH",
                    help="Files or directories to attach")
    pa.add_argument("--resume-url", metavar="URL",
                    help="Resume an existing Claude chat URL")
    pa.add_argument("--resume", action="store_true", help="Resume the last conversation")
    pa.add_argument("--new", action="store_true", help="Start a new chat (default)")

    args = ap.parse_args()
    logger.debug(f"Command run: {' '.join(sys.argv)}")
    logger.info("devloop starting...")

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("[devloop] Missing dependency. Run:")
        print("  pip install playwright --break-system-packages")
        print("  playwright install chromium")
        sys.exit(1)

    try:
        if args.mode == "run":
            mode_run(args)
        elif args.mode == "ask":
            mode_ask(args)
    except KeyboardInterrupt:
        print("\n[devloop] 🛑 Interrupted by user")
        # If we can find the page from the context of where we were, we could log it.
        # But main doesn't have the page. We'd need to catch it deeper or store it globally.
        # For now, just exit cleanly.
        sys.exit(130)


if __name__ == "__main__":
    main()