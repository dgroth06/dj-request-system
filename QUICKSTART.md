# ⚡ Quick Start Guide

Get your DJ Request System up and running in **15 minutes**!

## 🎯 What You Need

- ✅ Raspberry Pi 5 (with power supply)
- ✅ MicroSD card (64GB+) with Raspberry Pi OS installed
- ✅ Focusrite Scarlett Solo/2i2 (3rd Gen)
- ✅ XLR cables
- ✅ Internet connection (for initial setup only)

## 🚀 Three Steps to DJ Heaven

### Step 1: Flash Raspberry Pi OS (5 minutes)

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Insert microSD card into your computer
3. In Imager:
   - Choose: **Raspberry Pi OS (64-bit)** with Desktop
   - Click ⚙️ (gear icon) for settings:
     - Enable SSH
     - Set username: `pi`
     - Set password: (your choice)
     - Configure WiFi (your home network)
     - Set hostname: `djsystem`
   - Write to SD card
4. Insert SD card into Raspberry Pi and boot

### Step 2: Install System (10 minutes)

**Option A: From GitHub (Recommended)**

On Raspberry Pi terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/dj-request-system/main/github-install.sh | bash
```

**Option B: Manual Install**

1. Upload files to Raspberry Pi (via USB drive or SCP)
2. On Raspberry Pi:
   ```bash
   cd /home/pi/dj-request-system
   chmod +x install.sh
   ./install.sh
   ```

The installer will:
- ✅ Install all software
- ✅ Detect your Focusrite Scarlett
- ✅ Configure WiFi access point
- ✅ Test audio output
- ✅ Set up auto-start

**Wait 10-15 minutes for installation to complete.**

### Step 3: Connect & Test (2 minutes)

1. **Reboot**:
   ```bash
   sudo reboot
   ```

2. **Connect Focusrite Scarlett**:
   - Plug USB into Raspberry Pi
   - Connect XLR cables to mixer

3. **Test Audio**:
   ```bash
   cd ~/dj-request-system
   ./test-audio.sh
   ```
   You should hear a test tone from your speakers!

4. **Connect to WiFi**:
   - On your phone/laptop, connect to: `DJ-Requests`
   - Password: `DJParty2024`

5. **Open Browser**:
   - Go to: `http://192.168.4.1:3000`
   - You should see the request page!

## 🎉 You're Live!

### For Event Attendees:
1. Connect to `DJ-Requests` WiFi
2. Open browser → `http://192.168.4.1:3000`
3. Request songs!

### For DJs:
1. Connect to `DJ-Requests` WiFi  
2. Open browser → `http://192.168.4.1:3000/admin`
3. Control everything!

## 🎚️ First-Time Audio Setup

1. **Set Software Volume**: 80% (in admin panel)
2. **Set Scarlett Gain**: 12 o'clock position
3. **Adjust Mixer**: Normal operating level
4. **Test**: Play a song and adjust as needed

## ⚡ Quick Commands

```bash
# Check system status
cd ~/dj-request-system
./status.sh

# Test audio
./test-audio.sh

# Start manually (if needed)
./start.sh

# View logs
journalctl -u dj-request.service -f

# Restart system
sudo reboot
```

## 🆘 Something Not Working?

### No WiFi Network?
```bash
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
```

### No Audio?
```bash
# Check if Scarlett is connected
lsusb | grep -i focusrite

# Test audio
cd ~/dj-request-system
./test-audio.sh
```

### Web Page Not Loading?
```bash
# Check if server is running
sudo systemctl status dj-request.service

# Restart server
sudo systemctl restart dj-request.service
```

### Songs Not Downloading?
- ✅ Make sure you have internet connection during setup
- ✅ Songs need YouTube URLs to download
- ✅ Check disk space: `df -h`

## 🎯 Default Settings

| Setting | Value |
|---------|-------|
| WiFi Network | DJ-Requests |
| WiFi Password | DJParty2024 |
| IP Address | 192.168.4.1 |
| Web Port | 3000 |
| User Page | http://192.168.4.1:3000 |
| Admin Panel | http://192.168.4.1:3000/admin |

## 📱 Pro Tips

1. **Power**: Use official Raspberry Pi power supply (5V/5A)
2. **Cooling**: Add a fan to prevent overheating during long events
3. **Backup**: Create SD card image after setup (`dd` command)
4. **Updates**: Keep yt-dlp updated: `sudo yt-dlp -U`
5. **Storage**: Clean old songs: `rm ~/dj-request-system/Music/*.mp3`

## 🎵 Ready to Party!

Your system is now:
- ✅ Creating its own WiFi network
- ✅ Ready to accept requests
- ✅ Outputting professional audio via XLR
- ✅ Auto-starting on boot

**Just power on and you're DJing in 60 seconds!**

---

📖 Need more help? Check:
- **Full Documentation**: [README.md](README.md)
- **GitHub Setup**: [GITHUB_DEPLOYMENT.md](GITHUB_DEPLOYMENT.md)
- **Troubleshooting**: See README.md

**Questions?** Open an issue on GitHub!

🎉 **Have fun and happy DJing!** 🎉
