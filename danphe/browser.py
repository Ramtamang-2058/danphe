"""
browser.py — generic browser tools for the danphe agent.

Drives a persistent, visible Firefox session (profile at ~/.danphe/browser/)
so the agent can open any website, navigate, type, click, copy text, take
screenshots, and resolve real tasks — the same way ipo.py drives MeroShare
but with no site-specific logic.

Set DANPHE_BROWSER_HEADLESS=1 to run headless (off by default so demos show
the live browser window).
"""
from __future__ import annotations
import datetime
import os
import time
from pathlib import Path

BROWSER_DIR = Path.home() / ".danphe" / "browser"
TEXT_CAP = 12000
SCREENSHOT_DIR = Path("/tmp/danphe-shots")

_state: dict = {
    "playwright": None,
    "context": None,
    "page": None,
}


def _ensure_page():
    if _state["page"] is not None:
        return _state["page"]
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    headless = os.environ.get("DANPHE_BROWSER_HEADLESS", "") == "1"
    context = p.firefox.launch_persistent_context(
        user_data_dir=str(BROWSER_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    _state["playwright"] = p
    _state["context"] = context
    _state["page"] = page
    return page


def _goto(page, url: str) -> None:
    page.goto(url, wait_until="load", timeout=30000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) > TEXT_CAP:
        text = text[:TEXT_CAP] + f"\n… (truncated, {len(text)} chars total)"
    return text or "(no text on page)"


# ── Tool-facing API ───────────────────────────────────────────────────────────

def open() -> str:
    """Start the browser session (lazy, idempotent). Returns status."""
    page = _ensure_page()
    url = page.url or "(about:blank)"
    return (f"Browser open ({'headless' if page.context.browser else 'visible'} "
            f"Firefox, profile {BROWSER_DIR}). Current page: {url} ")


def go(url: str) -> str:
    """Navigate to a URL and return the page title + text preview."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = _ensure_page()
    try:
        _goto(page, url)
        title = page.title() or ""
        text = _truncate(page.inner_text("body"))
        preview = text[:300].replace("\n", " ") + ("…" if len(text) > 300 else "")
        return f"Navigated to {url}\nTitle: {title}\nPreview: {preview}"
    except Exception as e:
        return f"Error navigating to {url}: {e}"


def _settle(page) -> None:
    """Wait for the page to stop changing before reading its content.

    Waits for network idle, then re-reads the body text every second until
    it stops growing/changing (handles sites that render asynchronously).
    """
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    prev = None
    for _ in range(6):
        try:
            cur = page.inner_text("body", timeout=8000)
        except Exception:
            return
        if prev is not None and cur == prev:
            return
        prev = cur
        time.sleep(1)


def text() -> str:
    """Copy the visible text of the current page."""
    if _state["page"] is None:
        return "Error: no open session — call browser_open first."
    try:
        _settle(_state["page"])
        return _truncate(_state["page"].inner_text("body", timeout=10000))
    except Exception as e:
        return f"Error reading page text: {e}"


def copy(selector: str) -> str:
    """Copy text from an element matching a CSS selector (or text= selector)."""
    if _state["page"] is None:
        return "Error: no open session — call browser_open first."
    try:
        _settle(_state["page"])
        return _truncate(_state["page"].inner_text(selector, timeout=10000))
    except Exception as e:
        return f"Error: no element matching '{selector}': {e}"


def type_text(selector: str, text: str) -> str:
    """Fill a field matching a selector with the given text (clears it first)."""
    page = _ensure_page()
    try:
        page.fill(selector, text)
        return f"Typed {len(text)} chars into '{selector}'."
    except Exception as e:
        return f"Error typing into '{selector}': {e}"


def click(selector: str) -> str:
    """Click the first element matching a selector."""
    page = _ensure_page()
    try:
        page.click(selector, timeout=10000)
        time.sleep(1.5)
        return f"Clicked '{selector}'."
    except Exception as e:
        return f"Error clicking '{selector}': {e}"


def press(key: str) -> str:
    """Press a keyboard key (Enter, Tab, Escape, Backspace, etc.)."""
    page = _ensure_page()
    try:
        page.keyboard.press(key)
        time.sleep(1.5)
        return f"Pressed {key}."
    except Exception as e:
        return f"Error pressing {key}: {e}"


def screenshot(name: str = "") -> str:
    """Save a PNG screenshot of the current page and return its path."""
    if _state["page"] is None:
        return "Error: no open session — call browser_open first."
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%H%M%S")
    path = SCREENSHOT_DIR / f"{name or 'shot'}-{stamp}.png"
    try:
        _state["page"].screenshot(path=str(path))
        return f"Screenshot saved to {path}"
    except Exception as e:
        return f"Error taking screenshot: {e}"


def back() -> str:
    """Go back one page in history."""
    if _state["page"] is None:
        return "Error: no open session — call browser_open first."
    try:
        _state["page"].go_back(wait_until="load")
        return f"Went back to: {_state['page'].url}"
    except Exception as e:
        return f"Error going back: {e}"


def status() -> str:
    """Report browser session state."""
    page = _state["page"]
    if page is None:
        return "Browser session: closed"
    return (f"Browser session: open\n"
            f"URL: {page.url}\n"
            f"Title: {page.title() or ''}")


def close() -> str:
    """Close the browser session and clear cached page state."""
    if _state["context"] is not None:
        try:
            _state["context"].close()
        except Exception:
            pass
        _state["context"] = None
    if _state["playwright"] is not None:
        try:
            _state["playwright"].stop()
        except Exception:
            pass
        _state["playwright"] = None
    _state["page"] = None
    return "Browser session closed."
