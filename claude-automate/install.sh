#!/bin/bash
# install.sh — one-time setup for devloop

set -e
echo "=== devloop setup ==="

echo "[1/3] Installing Playwright..."
pip install playwright --break-system-packages
playwright install chromium

echo "[2/3] Installing devloop..."
sudo cp devloop.py /usr/local/bin/devloop
sudo chmod +x /usr/local/bin/devloop

echo "[3/3] Done!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Usage:"
echo ""
echo "  # Run a command — auto-fix on error:"
echo "  cd /your/project"
echo "  devloop run 'python app.py'"
echo "  devloop run 'pytest tests/'"
echo "  devloop run 'docker compose up'"
echo ""
echo "  # Ask Claude (replaces claude-cli):"
echo "  devloop ask 'what does this codebase do' -f ./src"
echo "  devloop ask 'review my models' -f models.py schemas.py"
echo "  devloop ask 'fix this bug' -f ./src ./tests"
echo "  devloop ask 'explain this error' --resume-url https://claude.ai/chat/abc123"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "NOTE: First run copies your Brave profile so Claude stays logged in."
echo "      Close Brave before first use of devloop."

