# 🦚 danphe

> Browser automation · Playwright · Python

![Python](https://img.shields.io/badge/Python-3.10+-green) ![Playwright](https://img.shields.io/badge/Playwright-Firefox-blue) ![Platform](https://img.shields.io/badge/Platform-Instagram%20%7C%20WhatsApp-orange)

Named after Nepal's national bird — the **Himalayan Monal** — danphe automates messaging across Instagram and WhatsApp using persistent browser sessions. No tokens, no APIs, just a real browser doing what you'd do.

---

## Scripts

| Script | Platform | Description |
|---|---|---|
| `send_dm.py` | Instagram | Single-target DM via profile page or DM inbox with session persistence |
| `msg.py` | Instagram · WhatsApp | Unified CLI for multi-platform messaging in one command |

---

## Install

```bash
# clone & enter
git clone https://github.com/yourname/danphe && cd danphe

# create venv
python3 -m venv venv && source venv/bin/activate

# install deps
pip install -r requirements.txt
playwright install firefox
```

---

## Usage

```bash
# instagram DM
python3 msg.py instagram its_ramtamang "Hey!"

# whatsapp message
python3 msg.py whatsapp "Ram Tamang" "Hey!"

# single instagram script
python3 send_dm.py
```

---

## First Run

1. A Firefox window opens automatically
2. Log in manually — session is saved to `browser_data/`
3. Press `ENTER` in the terminal when logged in
4. Subsequent runs skip login entirely

---

## Project Structure

```
danphe/
├── msg.py                   # Unified CLI entrypoint
├── send_dm.py               # Instagram-only script
├── requirements.txt         # Python dependencies
├── browser_data/            # Instagram session (auto-created)
├── browser_data_whatsapp/   # WhatsApp session (auto-created)
└── debug*.png               # Auto screenshots on error
```

---

## Requirements

```
playwright
```

Generate `requirements.txt` with:

```bash
pip freeze > requirements.txt
```

---

## Notes

- Sessions persist across runs — no repeated logins
- `debug.png` and `debug2.png` are saved automatically when something goes wrong
- WhatsApp requires QR scan on first run
- Instagram may prompt re-login if session expires

---

*danphe — named after the Himalayan Monal 🦚 · Nepal*