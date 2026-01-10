#!/bin/bash

# Sync to GitHub Script
# Usage: ./sync-to-github.sh [optional description]
# If no description provided, will auto-generate from changes

DESCRIPTION="$1"

echo "================================"
echo "Syncing to GitHub"
echo "================================"

# Add all changes first
git add .

# Show what's changed
echo ""
echo "Files that will be committed:"
git status --short

# Generate description if not provided
if [ -z "$DESCRIPTION" ]; then
    echo ""
    echo "Auto-generating commit description..."
    CHANGED_FILES=$(git diff --cached --name-only | xargs -n1 basename | head -5 | paste -sd ", " -)
    DESCRIPTION="Updated files: $CHANGED_FILES"
fi

# Create commit with timestamp and description
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo ""
echo "Commit message: $DESCRIPTION"
echo ""
echo "Creating commit..."
git commit -m "Update: $DESCRIPTION" -m "" -m "Timestamp: $TIMESTAMP" -m "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

if [ $? -ne 0 ]; then
    echo ""
    echo "No changes to commit."
    exit 0
fi

# Push to GitHub
echo ""
echo "Pushing to GitHub..."
git push origin main

echo ""
echo "================================"
echo "✓ Successfully synced to GitHub"
echo "================================"
echo ""
echo "Your Raspberry Pi can now pull the latest version with:"
echo "  cd ~/dj-request-system"
echo "  ./sync-from-github.sh"
