#!/bin/bash

# Sync to GitHub Script
# Usage: ./sync-to-github.sh "Brief description of changes"

if [ -z "$1" ]; then
    echo "Error: Please provide a description of your changes"
    echo "Usage: ./sync-to-github.sh \"Your change description\""
    exit 1
fi

DESCRIPTION="$1"

echo "================================"
echo "Syncing to GitHub"
echo "================================"

# Show what's changed
echo ""
echo "Files that will be committed:"
git status --short

# Add all changes
echo ""
echo "Adding files to git..."
git add .

# Create commit with timestamp and description
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
COMMIT_MSG="Update: $DESCRIPTION

Timestamp: $TIMESTAMP
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

echo ""
echo "Creating commit..."
git commit -m "$COMMIT_MSG"

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
echo "  git pull origin main"
