#!/bin/bash
###############################################################################
# Quick Setup Script - Deploy from GitHub
# Run this on your Raspberry Pi to install the entire system
###############################################################################

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     🎵 DJ Request System - GitHub Quick Install 🎵            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "⚠️  Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Git is installed
if ! command -v git &> /dev/null; then
    echo "📦 Installing Git..."
    sudo apt update
    sudo apt install -y git
fi

# Get repository URL from user
echo "📥 Enter your GitHub repository URL:"
echo "   (Example: https://github.com/username/dj-request-system.git)"
read -p "URL: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ No URL provided. Exiting."
    exit 1
fi

# Clone repository
INSTALL_DIR="/home/pi/dj-request-system"

if [ -d "$INSTALL_DIR" ]; then
    echo "⚠️  Directory already exists: $INSTALL_DIR"
    read -p "Remove and reinstall? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
    else
        echo "Installation cancelled."
        exit 1
    fi
fi

echo "📥 Cloning repository..."
git clone "$REPO_URL" "$INSTALL_DIR"

# Navigate to directory
cd "$INSTALL_DIR"

# Make installer executable
chmod +x install.sh

# Run installer
echo ""
echo "🚀 Starting installation..."
echo ""
./install.sh

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Reboot: sudo reboot"
echo "2. Connect to WiFi: DJ-Requests (password: DJParty2024)"
echo "3. Open browser: http://192.168.4.1:3000"
echo ""
