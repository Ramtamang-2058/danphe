# 🦚 danphe

> Browser automation · Playwright · Python · Claude AI Integration

![Python](https://img.shields.io/badge/Python-3.10+-green) ![Playwright](https://img.shields.io/badge/Playwright-Chromium%20%7C%20Firefox-blue) ![Platform](https://img.shields.io/badge/Platform-Instagram%20%7C%20WhatsApp%20%7C%20Claude-orange)

Named after Nepal's national bird — the **Himalayan Monal** — danphe automates messaging across Instagram and WhatsApp using persistent browser sessions. It also includes **devloop**, an agentic CLI that integrates with Claude AI for intelligent auto-fixing and code assistance. No tokens, no APIs, just real browsers doing what you'd do.

---

## 🎯 Main Tools

### 1️⃣ **devloop** — Agentic Claude CLI + Auto-Fixer
A powerful development assistant that uses Claude AI with browser automation to intelligently fix errors and answer questions.

**Features:**
- 🤖 **Agentic auto-fix loop**: Automatically tries to fix command errors and retry
- 📎 **File attachment**: Ask Claude to review code with full file/directory context
- 💬 **Interactive chat**: Keeps browser open for follow-up questions
- 🔄 **Code execution**: Auto-extracts and applies Claude's code suggestions
- 📦 **Proper formatting**: Claude's responses displayed in readable box format for easy copying

**Quick Start:**
```bash
# Ask Claude anything
devloop ask "how do I fix this?"

# Auto-fix errors
devloop run 'python app.py'      # If fails, Claude fixes it automatically

# Review code
devloop ask "review this" -f src/main.py

# Attach multiple files
devloop ask "optimize performance" -f ./src ./tests
```

**See Also:** [FIX_SUMMARY.md](FIX_SUMMARY.md) for detailed improvements | [IMPROVEMENTS.md](IMPROVEMENTS.md) for technical details

---

### 2️⃣ **Messaging Tools** — Instagram & WhatsApp Automation

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
playwright install chromium firefox    # For both devloop (Brave/Chromium) and messaging (Firefox)
```

**devloop-specific setup:**
```bash
# devloop needs Brave browser (or uses Playwright Chromium fallback)
sudo apt install brave-browser  # or snap install brave

# First run or clean slate:
rm -rf ~/.config/devloop-brave-profile
devloop ask "test"  # Browser opens, logs you into Claude, saves session
```

---

## Usage

### 🤖 devloop (Claude AI Assistant + Auto-Fixer)

```bash
# Interactive Q&A with Claude (browser stays open)
devloop ask "explain async/await in Python"
devloop ask "how do I debug this error?"

# Ask with code review
devloop ask "review this code" -f src/main.py
devloop ask "find bugs" -f ./src ./tests

# Auto-fix errors (automatically retries on success)
devloop run 'python app.py'        # If fails: Claude fixes → retry
devloop run 'npm test'             # Automatic error analysis + fix
devloop run 'poetry install'       # Agentic fixing

# Resume a previous chat
devloop ask "continue from here" --resume-url "https://claude.ai/chat/..."
```

### 📱 Messaging (Instagram/WhatsApp)

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

### devloop (Claude AI Integration)
1. `devloop ask "test"` opens a Brave window → Claude chat
2. Log in to your Claude account manually
3. Browser stays open, session is saved to `~/.config/devloop-brave-profile/`
4. Subsequent runs use saved session (instant startup!)

### Messaging Scripts
1. A Firefox window opens automatically
2. Log in manually — session is saved to `browser_data/`
3. Press `ENTER` in the terminal when logged in
4. Subsequent runs skip login entirely

---

## Project Structure

```
danphe/
├── devloop.py               # 🤖 Claude CLI + agentic auto-fixer
├── msg.py                   # Unified messaging CLI
├── send_dm.py               # Instagram-only script
├── requirements.txt         # Python dependencies
├── FIX_SUMMARY.md           # What was improved in devloop
├── IMPROVEMENTS.md          # Technical details of fixes
├── test-improvements.sh     # Test script for devloop
├── browser_data/            # Instagram session (auto-created)
├── browser_data_whatsapp/   # WhatsApp session (auto-created)
└── ~/.config/devloop-brave-profile/  # devloop Claude session (auto-created)
```

---

## Requirements

### Core
```
playwright       # Browser automation
```

### For devloop (Optional but Recommended)
```
playwright       # Browser automation
brave-browser    # Fast browser with Claude integration (or uses Playwright Chromium)
```

### For Messaging
```
playwright       # Firefox automation
```

Generate `requirements.txt`:
```bash
pip freeze > requirements.txt
```

---

## How It Works

### devloop Magic 🪄
1. **Agentic Loop**: Runs → Error? → Ask Claude → Extract fix → Apply → Retry
2. **Real Browser**: Uses your actual Brave browser with saved session
3. **No API Limits**: Uses Claude web interface (no token limits)
4. **Smart Extraction**:
   - Parses `# FILE: path` markers for file updates
   - Extracts ` ```bash ` blocks for commands
   - Applies patches and runs commands automatically
5. **Proper Format**: Claude responses displayed in readable boxes for easy copying

### Messaging Bots
- Persistent sessions saved to local browser profiles
- No re-authentication needed after first login
- Real browser automation (not headless) for reliability

---

## Notes

### devloop
- Sessions persist — Claude stays logged in across runs
- Clear prompt formatting ensures Claude replies in correct format
- Auto-applies code patches and runs shell commands
- Browser window stays open for debugging or follow-up questions

### Messaging
- Sessions persist across runs — no repeated logins
- `debug.png` and `debug2.png` saved automatically on error
- WhatsApp requires QR scan on first run
- Instagram may prompt re-login if session expires

---

## Recent Improvements ✨

**devloop v2 (April 2026)**
- ✅ Fixed permission denied errors on profile creation
- ✅ Proper format display for Claude responses (readable boxes)
- ✅ Better code block extraction (bash + file patches)
- ✅ True agentic auto-fix: detects errors → asks Claude → applies fixes → retries
- ✅ Enhanced prompt formatting so Claude knows exact output format

See [FIX_SUMMARY.md](FIX_SUMMARY.md) and [IMPROVEMENTS.md](IMPROVEMENTS.md) for details.

---

## Troubleshooting

### devloop won't start
```bash
# Clean profile and try again
rm -rf ~/.config/devloop-brave-profile
devloop ask "test"
```

### Claude response not extracted
- Check response is in proper format (``bash`` or ``python`` blocks)
- Use ` # FILE: path/to/file ` marker for file patches
- See FIX_SUMMARY.md for expected format examples

### Brave not found
```bash
sudo apt install brave-browser
# or devloop will use Playwright Chromium as fallback
```

---

*danphe — named after the Himalayan Monal 🦚 · Nepal*