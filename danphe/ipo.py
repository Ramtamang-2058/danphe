"""
ipo.py — native MeroShare IPO application tools for the danphe agent.

Drives a persistent, visible Firefox session through MeroShare login, IPO
availability checks, form fill, and submission. The interactive steps that
cannot be automated (master password entry, CAPTCHA solving) are handed to
the user: ipo_login prompts for the master password on the terminal, and
ipo_apply pauses for the user to solve the CAPTCHA in the browser window.

Credentials are read in place from the meroshare-ipo-applier repo's
encrypted vault (config/credentials.enc). Nothing is ever written there.
"""
from __future__ import annotations
import base64
import csv
import datetime
import getpass
import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MEROSHARE_REPO = Path.home() / "Documents" / "Projects" / "meroshare-ipo-applier"
CONFIG_DIR = MEROSHARE_REPO / "config"
VAULT_PATH = CONFIG_DIR / "credentials.enc"
SALT_PATH = CONFIG_DIR / ".salt"
FAMILY_CSV = CONFIG_DIR / "family_members.csv"
LOG_CSV = CONFIG_DIR / "applications_log.csv"
BROWSER_DIR = Path.home() / ".danphe" / "ipo-browser"

MEROSHARE_URL = "https://meroshare.cdsc.com.np/#/login"
ASBA_URL = "https://meroshare.cdsc.com.np/#/asba"

SELECTORS = {
    "dp_dropdown": "#selectBranch",
    "username_input": "#username",
    "password_input": "#password",
    "login_button": "button:has-text('Login')",
    "apply_for_issue_tab": "text=Apply for Issue",
    "issue_row": "tr:has-text('{company}')",
    "crn_input": "#crn",
    "units_input": "#appliedKitta",
    "pin_input": "#transactionPIN",
    "submit_button": "button:has-text('Apply')",
    "success_message": "text=Application submitted",
}

_state: dict = {
    "pw": None,
    "creds": {},
    "members": [],
    "idx": 0,
    "ipos": [],
    "company": "",
    "scrip": "",
    "playwright": None,
    "context": None,
    "page": None,
}


def _read_members() -> list[dict]:
    if not FAMILY_CSV.exists():
        return []
    with open(FAMILY_CSV, newline="", encoding="utf-8") as f:
        return [
            row for row in csv.DictReader(f)
            if row.get("active", "yes").strip().lower() == "yes"
        ]


def _unlock(password: str) -> dict:
    if not VAULT_PATH.exists():
        raise ValueError("vault not found (config/credentials.enc missing)")
    salt = SALT_PATH.read_bytes()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    f = Fernet(key)
    try:
        return json.loads(f.decrypt(VAULT_PATH.read_bytes()).decode())
    except InvalidToken:
        raise ValueError("wrong master password")


def _log_result(member: dict, company: str, scrip: str, units: str, status: str, remarks: str) -> None:
    file_exists = LOG_CSV.exists()
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "member_name", "client_id", "crn_number",
                "company_name", "scrip", "units_applied", "status", "remarks",
            ])
        writer.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            member["member_name"], member.get("client_id", ""), member.get("crn_number", ""),
            company, scrip, units, status, remarks,
        ])


def _ensure_session():
    if _state["page"] is not None:
        return _state["page"]
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    context = p.firefox.launch_persistent_context(
        user_data_dir=str(BROWSER_DIR),
        headless=False,
        viewport={"width": 1280, "height": 800},
    )
    page = context.new_page()
    _state["playwright"] = p
    _state["context"] = context
    _state["page"] = page
    return page


def _login(page, member: dict) -> bool:
    page.goto(MEROSHARE_URL)
    page.wait_for_load_state("networkidle")
    page.click(SELECTORS["dp_dropdown"])
    page.wait_for_timeout(1000)
    page.keyboard.type(member["bank_name"], delay=100)
    page.wait_for_timeout(1000)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    page.fill(SELECTORS["username_input"], member["_username"])
    page.fill(SELECTORS["password_input"], member["_password"])
    page.click(SELECTORS["login_button"])
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    return page.url.endswith("/dashboard")


def _list_ipos(page) -> list[dict]:
    page.goto(ASBA_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    try:
        page.click(SELECTORS["apply_for_issue_tab"])
        page.wait_for_timeout(2000)
    except Exception:
        pass
    body_text = page.inner_text("body")
    if "No Record(s) Found" in body_text:
        return []
    ipos = []
    for row in page.query_selector_all("table tbody tr"):
        cells = row.query_selector_all("td")
        if len(cells) >= 4:
            ipos.append({
                "name": cells[1].inner_text().strip(),
                "scrip": cells[2].inner_text().strip(),
                "type": cells[3].inner_text().strip(),
            })
    return ipos


# ── Tool-facing API ───────────────────────────────────────────────────────────

def status() -> str:
    lines = [f"Config dir: {CONFIG_DIR}"]
    lines.append(f"Vault: {'present' if VAULT_PATH.exists() else 'missing'}")
    if FAMILY_CSV.exists():
        with open(FAMILY_CSV, newline="", encoding="utf-8") as f:
            members = list(csv.DictReader(f))
        active = sum(1 for m in members if m.get("active", "yes").strip().lower() == "yes")
        lines.append(f"Family members: {len(members)} total, {active} active")
    else:
        lines.append("Family CSV: missing")
    lines.append(f"Browser session: {'open' if _state['page'] is not None else 'closed'}")
    if _state["members"] and _state["idx"] < len(_state["members"]):
        lines.append(f"Current member: {_state['idx'] + 1} of {len(_state['members'])}")
    if LOG_CSV.exists():
        with open(LOG_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        lines.append(f"Application log entries: {max(len(rows) - 1, 0)}")
    return "\n".join(lines)


def login() -> str:
    if _state["page"] is not None:
        return "Browser session already open. Use ipo_check, ipo_apply, ipo_submit, or ipo_close."
    if not VAULT_PATH.exists() or not FAMILY_CSV.exists():
        return (f"Error: config not found in the meroshare-ipo-applier repo ({CONFIG_DIR}). "
                "Run its setup wizard (python setup.py) there first.")
    try:
        pw = getpass.getpass("Master password for MeroShare vault: ")
    except Exception as e:
        return f"Error: could not read master password from terminal: {e}"
    try:
        creds = _unlock(pw)
    except ValueError as e:
        return f"Error: {e}"

    members = []
    for m in _read_members():
        cred = creds.get(m["member_name"])
        if not cred:
            continue
        m["_username"] = cred.get("username", "")
        m["_password"] = cred.get("password", "")
        m["_pin"] = cred.get("pin", "")
        members.append(m)
    if not members:
        return "Error: no active members have saved credentials in the vault."

    _state.update(pw=pw, creds=creds, members=members, idx=0, ipos=[])
    page = _ensure_session()
    if not _login(page, members[0]):
        return f"Error: MeroShare login failed for member 1 ({members[0]['member_name']})."
    ipos = _list_ipos(page)
    _state["ipos"] = ipos
    line = f"Logged in as member 1 of {len(members)}. "
    if ipos:
        line += "Available IPOs: " + "; ".join(
            f"{i['name']} ({i['scrip']})" for i in ipos)
    else:
        line += "No IPOs currently available."
    return line


def check() -> str:
    if _state["page"] is None:
        return "Error: no open session — call ipo_login first."
    ipos = _list_ipos(_state["page"])
    _state["ipos"] = ipos
    if not ipos:
        return "No IPOs currently available for application."
    return "\n".join(
        f"{i + 1}. {ipo['name']} ({ipo['scrip']}) — {ipo['type']}"
        for i, ipo in enumerate(ipos)
    )


def apply(company: str, scrip: str = "") -> str:
    if _state["page"] is None:
        return "Error: no open session — call ipo_login first."
    if _state["idx"] >= len(_state["members"]):
        return "Error: all members already processed."
    member = _state["members"][_state["idx"]]
    page = _state["page"]

    ipos = _state["ipos"] or _list_ipos(page)
    _state["ipos"] = ipos
    target = None
    for ipo in ipos:
        if company.lower() in ipo["name"].lower() or (
                scrip and scrip.lower() in ipo["scrip"].lower()):
            target = ipo
            break
    if not target:
        return (f"Error: '{company} ({scrip})' not in the available IPOs. "
                "Use ipo_check to list what is available.")

    units = (member.get("default_units") or "10").strip() or "10"
    page.goto(ASBA_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    try:
        page.click(SELECTORS["apply_for_issue_tab"])
        page.wait_for_timeout(1500)
    except Exception:
        pass
    try:
        page.click(SELECTORS["issue_row"].format(company=target["name"]))
        page.wait_for_timeout(2000)
    except Exception as e:
        return f"Error: could not select issue {target['name']}: {e}"
    try:
        page.fill(SELECTORS["crn_input"], member["crn_number"])
    except Exception:
        pass
    try:
        page.fill(SELECTORS["units_input"], units)
        pin = member.get("_pin", "")
        if pin:
            page.fill(SELECTORS["pin_input"], pin)
    except Exception as e:
        return f"Error: could not fill the application form: {e}"

    _state["company"] = company
    _state["scrip"] = scrip
    return (f"Form filled for {member['member_name']} — {units} units of "
            f"{target['name']} ({target['scrip']}). Solve the CAPTCHA in the "
            "browser window now, then tell me to continue and I will submit.")


def submit() -> str:
    if _state["page"] is None:
        return "Error: no open session."
    if _state["idx"] >= len(_state["members"]):
        return "Error: all members already processed — use ipo_close."
    member = _state["members"][_state["idx"]]
    page = _state["page"]
    units = (member.get("default_units") or "10").strip() or "10"

    try:
        page.click(SELECTORS["submit_button"])
        page.wait_for_selector(SELECTORS["success_message"], timeout=15000)
        _log_result(member, _state["company"], _state["scrip"], units, "Applied", "")
        status_msg = f"Applied successfully for {member['member_name']}."
    except Exception as e:
        _log_result(member, _state["company"], _state["scrip"], units, "Failed/Unconfirmed", str(e))
        status_msg = f"Could not confirm success for {member['member_name']}: {e}"

    _state["idx"] += 1
    if _state["idx"] < len(_state["members"]):
        nxt = _state["members"][_state["idx"]]
        if not _login(page, nxt):
            return (status_msg + f" Login failed for the next member ({nxt['member_name']}). "
                    "Use ipo_check to see status.")
        _state["ipos"] = _list_ipos(page)
        return (status_msg + f" Next member ready: {nxt['member_name']}. "
                "Call ipo_apply with the company and scrip to continue.")
    return status_msg + " All active members processed. Call ipo_close when done."


def close() -> str:
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
    _state.update(
        page=None, pw=None, creds={}, members=[], idx=0,
        ipos=[], company="", scrip="",
    )
    return "Browser session closed and cached credentials cleared."
