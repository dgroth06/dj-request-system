# 🍓 Raspberry Pi 5 - Complete Standalone DJ System

## 📦 One-Package Installation

This guide will create a **completely standalone** DJ request system on Raspberry Pi 5 that:
- ✅ Runs without internet (after initial setup)
- ✅ Creates its own WiFi network
- ✅ Has professional DJ crossfading
- ✅ Auto-starts on boot
- ✅ Fits in a backpack
- ✅ Outputs to XLR

---

## 🛠️ What You Need

### Hardware:
- Raspberry Pi 5 (4GB or 8GB RAM)
- MicroSD card (64GB+ recommended)
- USB-C power supply (official Pi 5 power supply recommended)
- USB audio interface with XLR outputs (Behringer UM2, Focusrite Scarlett, etc.)
- **Optional:** Case with cooling fan
- **Optional:** External WiFi adapter (if using Pi WiFi for access point)

### Software (we'll install):
- Raspberry Pi OS (64-bit)
- Node.js 18+
- Python 3
- Mixxx DJ software
- yt-dlp
- All dependencies

---

## 📝 Step-by-Step Installation

### PART 1: Prepare Raspberry Pi

#### 1. Install Raspberry Pi OS

**Using Raspberry Pi Imager (Recommended):**
1. Download: https://www.raspberrypi.com/software/
2. Insert microSD card
3. Select **Raspberry Pi OS (64-bit)** with desktop
4. Click gear icon for advanced options:
   - Set hostname: `djsystem`
   - Enable SSH
   - Set username: `pi`
   - Set password: (your choice)
   - Configure WiFi (for initial internet access)
5. Write to SD card
6. Insert into Pi and boot

#### 2. Initial Pi Setup

Connect monitor, keyboard, mouse and boot up. Then:

```bash
# Update system first
sudo apt update
sudo apt upgrade -y

# Reboot
sudo reboot
```

---

### PART 2: Transfer Files to Pi

You have several options:

#### Option A: USB Drive
1. Copy your project folder to a USB drive on your PC
2. Plug USB into Pi
3. Copy files:
```bash
cp -r /media/pi/USB_DRIVE/dj-request-system /home/pi/
```

#### Option B: SCP (if on same network)
From your PC:
```bash
scp -r dj-request-system pi@djsystem.local:/home/pi/
```

#### Option C: Git (if you have it on GitHub)
On the Pi:
```bash
git clone YOUR_GITHUB_URL
```

---

### PART 3: Run the Installer

On the Raspberry Pi:

```bash
# Navigate to project directory
cd /home/pi/dj-request-system

# Make installer executable
chmod +x install.sh

# Run installer
./install.sh
```

The installer will:
- ✅ Install Node.js, Python, Mixxx, yt-dlp
- ✅ Set up project structure
- ✅ Create auto-start services
- ✅ Configure WiFi access point
- ✅ Create desktop shortcut

**This takes about 10-15 minutes.**

---

### PART 4: Configure Mixxx (First Time)

1. **Open Mixxx** from Start Menu or desktop

2. **Set Music Directory:**
   - Options → Preferences → Library
   - Add: `/home/pi/dj-request-system/Music`
   - Click "Rescan Library"

3. **Configure Audio Output:**
   - Options → Preferences → Sound Hardware
   - **Master Output:** Select your USB audio interface
   - **Sample Rate:** 44100 Hz
   - **Latency:** 20-50 ms

4. **Enable Auto-DJ:**
   - Options → Preferences → Auto DJ
   - ✅ Enable Auto DJ
   - **Transition:** Full Intro + Outro
   - **Transition Time:** 10 seconds
   - **Minimum Available:** 5 tracks

5. **Load Playlist:**
   - View → Show Auto DJ
   - In sidebar: Playlists → Right-click → "Import Playlist"
   - Browse to: `/home/pi/.mixxx/playlists/dj_queue.m3u`

6. **Save and close Mixxx**

---

### PART 5: Test the System

#### Start Everything:

Double-click **"DJ-Request-System"** icon on desktop

Or manually:
```bash
cd /home/pi/dj-request-system
./start-dj-system.sh
```

#### Connect to WiFi:

On your phone/laptop:
- **SSID:** DJ-Requests
- **Password:** DJParty2024

#### Access Interface:

- **User requests:** http://192.168.4.1:3000
- **Admin dashboard:** http://192.168.4.1:3000/admin-player.html
- **Settings:** http://192.168.4.1:3000/settings.html

#### Test Flow:

1. Request a song from user interface
2. Watch Python bridge download it (check terminal)
3. Open Mixxx - song should appear in Auto-DJ
4. Click "Enable Auto DJ" in Mixxx
5. Song plays with next song crossfading in!

---

## 🚀 Make It Auto-Start on Boot

```bash
# Enable services
sudo systemctl enable dj-backend
sudo systemctl enable dj-bridge

# Add Mixxx to autostart
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/mixxx.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Mixxx
Exec=mixxx
EOF

# Reboot to test
sudo reboot
```

Now when Pi boots:
1. Backend starts automatically
2. Bridge starts automatically  
3. Mixxx opens automatically
4. WiFi access point starts
5. **System is ready in ~60 seconds!**

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────┐
│           Raspberry Pi 5                     │
│  ┌────────────┐  ┌──────────────┐           │
│  │  Node.js   │  │    Python    │           │
│  │  Backend   │←→│    Bridge    │           │
│  │  (port     │  │ (downloads   │           │
│  │   3000)    │  │  songs)      │           │
│  └────────────┘  └──────┬───────┘           │
│       ↑                  ↓                    │
│  ┌────┴──────┐  ┌───────────────┐           │
│  │   WiFi    │  │     Mixxx     │           │
│  │  Access   │  │   (Auto-DJ    │           │
│  │   Point   │  │ crossfading)  │           │
│  └───────────┘  └───────┬───────┘           │
│                          ↓                    │
│                  ┌───────────────┐           │
│                  │  USB Audio    │           │
│                  │  Interface    │           │
└──────────────────┴───────┬───────┴───────────┘
                            ↓
                    🔊 XLR Output to Mixer
```

---

## 🔧 Troubleshooting

### Services Not Starting

```bash
# Check status
sudo systemctl status dj-backend
sudo systemctl status dj-bridge

# View logs
sudo journalctl -u dj-backend -f
sudo journalctl -u dj-bridge -f

# Restart
sudo systemctl restart dj-backend
sudo systemctl restart dj-bridge
```

### Songs Not Downloading

```bash
# Test yt-dlp manually
yt-dlp --version
yt-dlp "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Check bridge logs
sudo journalctl -u dj-bridge -f
```

### WiFi Access Point Not Working

```bash
# Check services
sudo systemctl status hostapd
sudo systemctl status dnsmasq

# Restart
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
```

### Mixxx Not Crossfading

1. Check Auto-DJ is enabled
2. Verify transition time is set (10 seconds)
3. Make sure "Full Intro + Outro" is selected
4. Check at least 2 songs are in queue

### Audio Not Coming Out

1. Check Mixxx audio settings
2. Verify USB interface is connected
3. Test with: `aplay -l` (should show your interface)
4. In Mixxx: Options → Sound Hardware → Select correct device

---

## 💾 Storage Management

Songs are stored in: `/home/pi/dj-request-system/Music/`

**Check storage:**
```bash
df -h
du -sh /home/pi/dj-request-system/Music/
```

**Clean up old songs:**
```bash
# Delete songs older than 30 days
find /home/pi/dj-request-system/Music/ -type f -mtime +30 -delete
```

**Recommended:**
- 64GB SD card = ~40-50 songs
- 128GB SD card = ~90-100 songs
- 256GB SD card = ~200+ songs

---

## 🎚️ Customization

### Change WiFi Network Name/Password

Edit: `/etc/hostapd/hostapd.conf`
```bash
sudo nano /etc/hostapd/hostapd.conf

# Change:
ssid=YOUR_EVENT_NAME
wpa_passphrase=YOUR_PASSWORD

# Restart
sudo systemctl restart hostapd
```

### Change Crossfade Duration

In Mixxx:
- Options → Preferences → Auto DJ → Transition Time
- Short (4-6 sec): Fast-paced events
- Medium (8-12 sec): Standard
- Long (15-20 sec): Lounge/ambient

### Add Default Songs

Use the Playlist Manager interface:
http://192.168.4.1:3000/playlist-manager.html

---

## 📦 Creating a Backup Image

Once everything is working perfectly:

```bash
# On your PC (not Pi)
# Insert SD card
sudo dd if=/dev/sdX of=dj-system-backup.img bs=4M status=progress

# Compress
gzip dj-system-backup.img
```

Now you can flash this image to new SD cards for instant deployment!

---

## 🎉 You're Done!

Your Raspberry Pi is now a **complete, standalone DJ request system** that:

✅ Creates its own WiFi network
✅ Runs without internet
✅ Professional crossfading
✅ Auto-downloads songs
✅ XLR audio output
✅ Auto-starts on boot
✅ Fits in a backpack

**Just plug in power and you're DJing in 60 seconds!** 🎵