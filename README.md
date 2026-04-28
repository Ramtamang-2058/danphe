# 🦚 danphe

> Browser automation for Instagram & WhatsApp — named after Nepal's national bird, the Himalayan Monal.

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue)
![Playwright](https://img.shields.io/badge/Playwright-Firefox-orange)

No tokens. No APIs. Just a real browser doing what you'd do.

---

## Features

- Send Instagram DMs via profile page or inbox
- Send WhatsApp messages via WhatsApp Web
- Persistent browser sessions — log in once, reuse forever
- Auto debug screenshots on failure (`debug.png`, `debug2.png`)

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

### Unified CLI (`msg.py`)

```bash
# Instagram DM
python3 msg.py instagram its_ramtamang "Hey!"

# WhatsApp message
python3 msg.py whatsapp "Ram Tamang" "Hey!"
```

### Single Instagram script (`send_dm.py`)

Edit `TARGET_USER` and `MESSAGE` at the top of the file, then:

```bash
python3 send_dm.py
```

---

## First Run

1. A Firefox window opens automatically
2. Log in manually in the browser window
3. Press `ENTER` in the terminal when done
4. Session is saved to `browser_data/` — subsequent runs skip login

---

## Project Structure

```
danphe/
├── msg.py                   # Unified CLI — Instagram + WhatsApp
├── send_dm.py               # Instagram-only standalone script
├── requirements.txt         # Python dependencies
├── browser_data/            # Persistent Instagram session (auto-created)
├── browser_data_whatsapp/   # Persistent WhatsApp session (auto-created)
├── debug.png                # Auto screenshot on search step failure
└── debug2.png               # Auto screenshot on message step failure
```

---

## Requirements

```
playwright
```

Generate `requirements.txt`:

```bash
pip freeze > requirements.txt
```

Or minimal:

```bash
echo "playwright" > requirements.txt
```

---

## Notes

- Uses **Firefox** with persistent context — sessions survive restarts
- WhatsApp requires QR scan on first run
- Instagram may show a "suspicious login" prompt — confirm it in the browser
- `debug.png` / `debug2.png` are saved automatically when something goes wrong — check them first before debugging

---

## Disclaimer

This tool is for personal use only. Automating messages may violate Instagram's and WhatsApp's Terms of Service. Use responsibly.

---

*danphe — named after the Himalayan Monal 🦚 · Nepal*
