#!/usr/bin/env bash
# Run this from inside ~/Documents/Projects/danphe/
# It reorganizes flat files into the correct package structure

set -e
CWD="$(pwd)"
echo "[danphe] Fixing structure in $CWD"

# 1. Create correct directories
mkdir -p danphe/llm tools plugins

# 2. Move flat files into danphe/ package
for f in cli.py agent.py config.py router.py patches.py; do
    [ -f "$f" ] && mv "$f" danphe/ && echo "  moved $f → danphe/$f"
done

# 3. Move LLM files
for f in nvidia.py gemini.py; do
    [ -f "$f" ] && mv "$f" danphe/llm/ && echo "  moved $f → danphe/llm/$f"
done

# 4. Move tools
for f in file_tool.py shell_tool.py; do
    [ -f "$f" ] && mv "$f" tools/ && echo "  moved $f → tools/$f"
done

# 5. Rename env.example if needed
[ -f "env.example" ] && mv env.example .env.example && echo "  renamed env.example → .env.example"

# 6. Create __init__.py files if missing
touch danphe/__init__.py danphe/llm/__init__.py tools/__init__.py plugins/__init__.py

# 7. Reinstall
echo ""
echo "[danphe] Reinstalling..."
pip install -e . --break-system-packages -q

echo ""
echo "[danphe] Done! Run: danphe"
echo ""
echo "NEXT: copy .env.example to .env and add your API keys:"
echo "  cp .env.example .env"
echo "  nano .env"
