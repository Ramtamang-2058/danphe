#!/usr/bin/env bash
# update.sh - Update the installed version of danphe for local development

echo "Updating danphe..."

# Check if we're in a git repository
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Pulling latest changes from git..."
    git pull
    if [ $? -ne 0 ]; then
        echo "Warning: git pull failed. Continuing with local update..."
    fi
else
    echo "Not a git repository, skipping git pull..."
fi

# Re-install the package in editable mode using pip
echo "Reinstalling package..."
pip install -e . --break-system-packages

echo "Update complete! You can now use the 'danphe' command globally."
