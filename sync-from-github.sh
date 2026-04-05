#!/bin/bash

# Sync FROM GitHub Script (for Raspberry Pi)
# This script safely pulls the latest changes from GitHub
# Usage: ./sync-from-github.sh

echo "================================"
echo "Pulling latest from GitHub"
echo "================================"

# Check if there are local changes
if [[ -n $(git status -s) ]]; then
    echo ""
    echo "Warning: You have local changes:"
    git status --short
    echo ""
    read -p "Do you want to stash these changes and pull? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stashing local changes..."
        git stash
        STASHED=true
    else
        echo "Pull cancelled. Commit or discard your changes first."
        exit 1
    fi
fi

# Fetch latest changes
echo ""
echo "Fetching from GitHub..."
git fetch origin

# Pull with merge strategy
echo ""
echo "Pulling changes..."
git pull origin main --no-rebase

if [ $? -eq 0 ]; then
    echo ""
    echo "================================"
    echo "✓ Successfully synced from GitHub"
    echo "================================"

    # Restore stashed changes if any
    if [ "$STASHED" = true ]; then
        echo ""
        echo "Restoring your stashed changes..."
        git stash pop
    fi

    # Check if services need restart
    echo ""
    echo "If you updated server.js or auto_player.py, you may need to restart services:"
    echo "  sudo systemctl restart dj-request.service"
    echo "  sudo systemctl restart dj-autoplayer.service"
else
    echo ""
    echo "================================"
    echo "✗ Pull failed"
    echo "================================"
    echo ""
    echo "Try resolving conflicts manually or run:"
    echo "  git reset --hard origin/main  (WARNING: discards all local changes)"
    exit 1
fi
