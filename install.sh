#!/bin/bash
###############################################################################
# DJ Request System - Complete One-Click Installer for Raspberry Pi
# Includes Focusrite Scarlett Solo 2i2 3rd Gen USB Audio Support
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        🎵 DJ Request System Installer for Raspberry Pi 🎵      ║"
echo "╠════════════════════════════════════════════════════════════════╣"
echo "║  This will install:                                            ║"
echo "║  • Node.js backend server                                      ║"
echo "║  • Python audio player bridge                                  ║"
echo "║  • yt-dlp for downloading songs                               ║"
echo "║  • Focusrite Scarlett USB audio driver support               ║"
echo "║  • WiFi Access Point configuration                            ║"
echo "║  • Auto-start on boot                                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}❌ Please don't run as root. Run as normal user (pi).${NC}"
   exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_DIR="/home/pi/dj-request-system"

echo -e "${YELLOW}📦 Installation will proceed in: $INSTALL_DIR${NC}"
echo ""

# Create installation directory if it doesn't exist
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${GREEN}Creating installation directory...${NC}"
    mkdir -p "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Update system
echo -e "${GREEN}🔄 Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

# Install Node.js 18+
echo -e "${GREEN}📦 Installing Node.js...${NC}"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt install -y nodejs
fi
echo -e "${BLUE}Node version: $(node --version)${NC}"
echo -e "${BLUE}NPM version: $(npm --version)${NC}"

# Install Python and pip
echo -e "${GREEN}🐍 Installing Python dependencies...${NC}"
sudo apt install -y python3 python3-pip python3-venv

# Install audio libraries for Focusrite Scarlett
echo -e "${GREEN}🎚️ Installing audio libraries for Focusrite Scarlett USB interface...${NC}"
sudo apt install -y \
    alsa-utils \
    alsa-base \
    libasound2-dev \
    pulseaudio \
    pulseaudio-utils \
    pavucontrol \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg

# Install yt-dlp (better than youtube-dl)
echo -e "${GREEN}⬇️ Installing yt-dlp...${NC}"
if [ ! -f "/usr/local/bin/yt-dlp" ]; then
    sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
    sudo chmod a+rx /usr/local/bin/yt-dlp
fi

# Install mpv media player for high-quality audio playback
echo -e "${GREEN}🎵 Installing mpv media player...${NC}"
sudo apt install -y mpv

# Create project structure
echo -e "${GREEN}📁 Creating project structure...${NC}"
mkdir -p "$INSTALL_DIR/Music"
mkdir -p "$INSTALL_DIR/public"
mkdir -p "$INSTALL_DIR/data"

# Create package.json
echo -e "${GREEN}📝 Creating package.json...${NC}"
cat > "$INSTALL_DIR/package.json" << 'EOF'
{
  "name": "dj-request-system",
  "version": "2.0.0",
  "description": "Standalone DJ Request System for Raspberry Pi",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "dev": "nodemon server.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "cors": "^2.8.5",
    "ytmusic-api": "^4.3.0",
    "sqlite3": "^5.1.6",
    "socket.io": "^4.6.1",
    "ytdl-core": "^4.11.5",
    "fluent-ffmpeg": "^2.1.2"
  },
  "devDependencies": {
    "nodemon": "^3.0.1"
  }
}
EOF

# Install Node.js dependencies
echo -e "${GREEN}📦 Installing Node.js packages (this may take a few minutes)...${NC}"
npm install

# Install Python dependencies
echo -e "${GREEN}🐍 Installing Python packages...${NC}"
pip3 install --break-system-packages flask requests

# Configure ALSA for Focusrite Scarlett
echo -e "${GREEN}🎚️ Configuring ALSA for Focusrite Scarlett USB Audio...${NC}"
cat > "$HOME/.asoundrc" << 'EOF'
# ALSA configuration for Focusrite Scarlett Solo/2i2
# This ensures the USB audio interface is used as default

pcm.!default {
    type plug
    slave.pcm "hw:CARD=USB,DEV=0"
}

ctl.!default {
    type hw
    card USB
}
EOF

# Configure PulseAudio for USB audio
echo -e "${GREEN}🔊 Configuring PulseAudio for USB audio...${NC}"
mkdir -p "$HOME/.config/pulse"
cat > "$HOME/.config/pulse/default.pa" << 'EOF'
# PulseAudio configuration for USB audio interface

# Load drivers
.include /etc/pulse/default.pa

# Set USB audio as default sink
set-default-sink alsa_output.usb-Focusrite_Scarlett_Solo_USB-00.analog-stereo
set-default-source alsa_input.usb-Focusrite_Scarlett_Solo_USB-00.analog-stereo
EOF

# Detect and configure Focusrite Scarlett
echo -e "${YELLOW}🔍 Detecting Focusrite Scarlett USB Audio Interface...${NC}"
if lsusb | grep -i "focusrite"; then
    echo -e "${GREEN}✅ Focusrite Scarlett detected!${NC}"
    # Get card number
    CARD_NUM=$(aplay -l | grep -i "scarlett\|focusrite" | head -n1 | cut -d: -f1 | grep -o '[0-9]*')
    if [ ! -z "$CARD_NUM" ]; then
        echo -e "${GREEN}Card number: $CARD_NUM${NC}"
        # Test audio output
        echo -e "${YELLOW}Testing audio output...${NC}"
        speaker-test -c2 -twav -D plughw:$CARD_NUM,0 -l1 2>/dev/null || true
    fi
else
    echo -e "${YELLOW}⚠️  Focusrite Scarlett not detected. Please connect it and rerun.${NC}"
    echo -e "${YELLOW}   Continuing with installation...${NC}"
fi

# WiFi Access Point Configuration
echo -e "${GREEN}📡 Configuring WiFi Access Point...${NC}"
sudo apt install -y hostapd dnsmasq

# Stop services
sudo systemctl stop hostapd 2>/dev/null || true
sudo systemctl stop dnsmasq 2>/dev/null || true

# Configure hostapd
echo -e "${YELLOW}Setting up access point configuration...${NC}"
sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
interface=wlan0
driver=nl80211
ssid=DJ-Requests
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=DJParty2024
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# Configure dnsmasq
sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig 2>/dev/null || true
sudo tee /etc/dnsmasq.conf > /dev/null << 'EOF'
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
domain=wlan
address=/djrequests.local/192.168.4.1
EOF

# Configure static IP
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    sudo tee -a /etc/dhcpcd.conf > /dev/null << 'EOF'

interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF
fi

# Point hostapd to config file
sudo sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

# Enable services
echo -e "${GREEN}Enabling WiFi services...${NC}"
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

# Create systemd service for auto-start
echo -e "${GREEN}⚙️ Creating auto-start service...${NC}"
sudo tee /etc/systemd/system/dj-request.service > /dev/null << EOF
[Unit]
Description=DJ Request System
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/node $INSTALL_DIR/server.js
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable dj-request.service

# Create desktop shortcut
echo -e "${GREEN}🖥️ Creating desktop shortcut...${NC}"
mkdir -p "$HOME/Desktop"
cat > "$HOME/Desktop/dj-system.desktop" << EOF
[Desktop Entry]
Name=DJ Request System
Comment=Start DJ Request System
Exec=lxterminal -e "cd $INSTALL_DIR && node server.js"
Icon=audio-headphones
Terminal=true
Type=Application
Categories=AudioVideo;
EOF
chmod +x "$HOME/Desktop/dj-system.desktop"

# Create helper scripts
echo -e "${GREEN}📜 Creating helper scripts...${NC}"

# Start script
cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
echo "🎵 Starting DJ Request System..."
echo "Access at: http://192.168.4.1:3000"
echo "Press Ctrl+C to stop"
node server.js
EOF
chmod +x "$INSTALL_DIR/start.sh"

# Status script
cat > "$INSTALL_DIR/status.sh" << 'EOF'
#!/bin/bash
echo "=== DJ Request System Status ==="
echo ""
echo "Service Status:"
systemctl status dj-request.service --no-pager | head -n 10
echo ""
echo "WiFi Access Point:"
systemctl status hostapd --no-pager | head -n 3
echo ""
echo "Audio Devices:"
aplay -l | grep -i "card\|scarlett\|focusrite"
echo ""
echo "USB Devices:"
lsusb | grep -i "focusrite"
EOF
chmod +x "$INSTALL_DIR/status.sh"

# Audio test script
cat > "$INSTALL_DIR/test-audio.sh" << 'EOF'
#!/bin/bash
echo "🎵 Testing Focusrite Scarlett Audio Output..."
echo ""
echo "Connected USB Audio Devices:"
aplay -l | grep -i "card\|scarlett\|focusrite"
echo ""
CARD_NUM=$(aplay -l | grep -i "scarlett\|focusrite" | head -n1 | cut -d: -f1 | grep -o '[0-9]*')
if [ ! -z "$CARD_NUM" ]; then
    echo "Testing audio on card $CARD_NUM..."
    speaker-test -c2 -twav -D plughw:$CARD_NUM,0 -l1
    echo "✅ Audio test complete!"
else
    echo "❌ No Focusrite Scarlett detected!"
fi
EOF
chmod +x "$INSTALL_DIR/test-audio.sh"

# Installation complete
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    ✅ Installation Complete! ✅                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📦 Installation Directory: $INSTALL_DIR${NC}"
echo -e "${BLUE}📡 WiFi Network: DJ-Requests${NC}"
echo -e "${BLUE}🔑 Password: DJParty2024${NC}"
echo -e "${BLUE}🌐 Access URL: http://192.168.4.1:3000${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1️⃣  Copy your server files to: $INSTALL_DIR"
echo -e "2️⃣  Test audio: ./test-audio.sh"
echo -e "3️⃣  Start system: ./start.sh"
echo -e "4️⃣  Or reboot to auto-start"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "  Check status: ./status.sh"
echo -e "  Test audio: ./test-audio.sh"
echo -e "  Manual start: ./start.sh"
echo -e "  View logs: journalctl -u dj-request.service -f"
echo ""
echo -e "${GREEN}🎉 Ready to DJ! Reboot to activate WiFi access point.${NC}"
