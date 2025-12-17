# 🎵 DJ Request System for Raspberry Pi

A complete, standalone DJ request system that runs on Raspberry Pi with Focusrite Scarlett Solo 2i2 (3rd Gen) USB audio support. Perfect for DJs, parties, events, and venues!

## ✨ Features

- 🎧 **Professional Audio**: Full support for Focusrite Scarlett USB audio interfaces
- 📡 **Self-Contained WiFi**: Creates its own WiFi network (no internet required after setup)
- 🎵 **Song Requests**: Users submit requests via mobile/web
- ⬇️ **Auto-Download**: Automatically downloads songs from YouTube
- 🎚️ **Crossfade**: Professional audio crossfading between tracks
- 🔊 **XLR Output**: Direct XLR output to mixer
- 📱 **Mobile-Friendly**: Works on any device with a web browser
- 🎛️ **DJ Control Panel**: Full control over queue, playback, and settings
- 🔄 **Auto-Start**: Boots up ready to go

## 🛠️ Hardware Requirements

### Required
- **Raspberry Pi 5** (4GB or 8GB RAM recommended)
- **MicroSD Card** (64GB+ recommended, Class 10 or better)
- **USB-C Power Supply** (Official Raspberry Pi 5 power supply recommended - 5V/5A)
- **Focusrite Scarlett Solo or 2i2 (3rd Gen)** USB audio interface
- **XLR Cables** (to connect to mixer/speakers)

### Optional
- Case with cooling fan
- External WiFi adapter (if you want to use Pi's built-in WiFi for internet while hosting access point)
- USB hub if connecting multiple devices

## 💿 Focusrite Scarlett Solo 2i2 (3rd Gen) Support

This system is specifically configured for the Focusrite Scarlett Solo 2i2 3rd Generation USB audio interface. The installer will:

✅ Automatically detect your Focusrite Scarlett device  
✅ Configure ALSA for optimal USB audio performance  
✅ Set up PulseAudio with proper routing  
✅ Test audio output during installation  
✅ Ensure 24-bit/192kHz audio quality support

### Why Focusrite Scarlett?

- **Professional Quality**: Studio-grade audio with low latency
- **XLR Outputs**: Direct connection to professional sound systems
- **Linux Compatible**: Works perfectly with Raspberry Pi (no special drivers needed!)
- **Reliable**: USB Class Compliant (plug and play)
- **Balanced Outputs**: Clean audio signal without interference

### Supported Models
- Focusrite Scarlett Solo (3rd Gen)
- Focusrite Scarlett 2i2 (3rd Gen)
- Focusrite Scarlett 4i4 (3rd Gen)
- Other USB Class Compliant audio interfaces

## 📦 Installation

### Step 1: Prepare Your Raspberry Pi

1. **Flash Raspberry Pi OS**:
   - Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
   - Flash **Raspberry Pi OS (64-bit)** with Desktop
   - Configure WiFi and SSH in advanced settings
   - Insert SD card and boot Pi

2. **Initial Setup**:
```bash
# Update system
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### Step 2: Connect Hardware

1. Connect Focusrite Scarlett Solo to Raspberry Pi USB port
2. Connect XLR cables from Scarlett to your mixer/speakers
3. Power on the Raspberry Pi
4. Verify Scarlett is detected:
```bash
lsusb | grep -i focusrite
# Should show: "Focusrite-Novation Scarlett Solo USB"
```

### Step 3: Run the Installer

1. **Download or clone this repository**:
```bash
cd ~
# If using Git:
git clone <your-repo-url> dj-request-system
cd dj-request-system

# OR manually copy files to Raspberry Pi
```

2. **Make the installer executable**:
```bash
chmod +x install.sh
```

3. **Run the installer**:
```bash
./install.sh
```

The installer will automatically:
- Install Node.js, Python, and dependencies
- Set up the database
- Configure Focusrite Scarlett USB audio
- Set up WiFi access point
- Create auto-start services
- Test audio output

**Installation takes 10-15 minutes.**

### Step 4: Copy Web Files

The installer creates the directory structure. Now copy the web interface files:

```bash
# Copy index.html and admin.html to the public directory
cp index.html /home/pi/dj-request-system/public/
cp admin.html /home/pi/dj-request-system/public/

# Copy server.js to the main directory
cp server.js /home/pi/dj-request-system/

# Copy audio_player.py to the main directory
cp audio_player.py /home/pi/dj-request-system/
chmod +x /home/pi/dj-request-system/audio_player.py
```

### Step 5: First Boot

```bash
# Reboot to activate WiFi access point
sudo reboot
```

## 🚀 Usage

### Starting the System

**Option 1: Auto-Start (Recommended)**
The system automatically starts on boot. Just power on the Pi!

**Option 2: Manual Start**
```bash
cd ~/dj-request-system
./start.sh
```

### Accessing the System

1. **Connect to WiFi**:
   - Network Name: `DJ-Requests`
   - Password: `DJParty2024`

2. **Open Web Browser**:
   - User Request Page: `http://192.168.4.1:3000`
   - DJ Admin Panel: `http://192.168.4.1:3000/admin`

### For Users (Making Requests)

1. Connect to the `DJ-Requests` WiFi network
2. Open browser and go to `http://192.168.4.1:3000`
3. Fill in song details
4. Submit request
5. Your request appears in the DJ's queue!

### For DJs (Admin Panel)

1. Go to `http://192.168.4.1:3000/admin`
2. See all incoming requests
3. Download songs (if not already downloaded)
4. Control playback (play, pause, stop, skip)
5. Adjust volume
6. Manage queue

## 🎚️ Audio Configuration

### Testing Audio Output

```bash
# Run the audio test script
cd ~/dj-request-system
./test-audio.sh
```

This will:
1. Show connected audio devices
2. Play a test tone through the Focusrite Scarlett
3. Verify XLR output is working

### Volume Levels

- **Software Volume**: 0-100% (controlled via admin panel)
- **Hardware Volume**: Use the gain knobs on your Focusrite Scarlett
- **Mixer Volume**: Final output level on your mixing board

**Recommended Setup**:
- Set software volume to 80-90%
- Adjust Scarlett output gain to 12 o'clock
- Fine-tune with mixer faders

### Audio Quality Settings

The system is configured for:
- **Sample Rate**: 48kHz (optimal for live audio)
- **Bit Depth**: 24-bit
- **Channels**: Stereo (2 channels)
- **Format**: MP3 320kbps (downloaded songs)

## 🔧 Configuration

### Change WiFi Network Name/Password

```bash
sudo nano /etc/hostapd/hostapd.conf

# Edit these lines:
ssid=YOUR_EVENT_NAME
wpa_passphrase=YOUR_PASSWORD

# Restart service
sudo systemctl restart hostapd
```

### Change Server Port

Edit `server.js`:
```javascript
const PORT = process.env.PORT || 3000; // Change 3000 to your port
```

### Audio Device Selection

The system auto-detects Focusrite Scarlett. To manually specify:

Edit `audio_player.py`:
```python
AUDIO_DEVICE = 'plughw:CARD=1,DEV=0'  # Change card number if needed
```

## 🐛 Troubleshooting

### Focusrite Scarlett Not Detected

```bash
# Check if connected
lsusb | grep -i focusrite

# List audio devices
aplay -l

# Check for USB device
dmesg | grep -i focusrite
```

**Solution**: Try a different USB port, preferably USB 3.0 (blue ports)

### No Audio Output

1. **Check connections**: XLR cables properly connected
2. **Check gain**: Turn up output gain on Scarlett interface
3. **Check mixer**: Ensure mixer channel is unmuted and turned up
4. **Test audio**: Run `./test-audio.sh`

### WiFi Access Point Not Working

```bash
# Check services
sudo systemctl status hostapd
sudo systemctl status dnsmasq

# Restart services
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
```

### Songs Not Downloading

```bash
# Update yt-dlp
sudo yt-dlp -U

# Check internet connection
ping google.com

# Check disk space
df -h
```

### System Not Auto-Starting

```bash
# Check service status
sudo systemctl status dj-request.service

# Enable service
sudo systemctl enable dj-request.service

# Check logs
journalctl -u dj-request.service -f
```

## 📊 System Status

Check system status:
```bash
cd ~/dj-request-system
./status.sh
```

View logs:
```bash
# Server logs
journalctl -u dj-request.service -f

# System logs
sudo dmesg | tail -50
```

## 🔄 Updating

```bash
cd ~/dj-request-system
git pull origin main  # If using Git
npm install  # Update Node packages
sudo reboot
```

## 💾 Backup

Create a backup image of your SD card:
```bash
# On your PC (not Pi)
# Insert SD card
sudo dd if=/dev/sdX of=dj-system-backup.img bs=4M status=progress

# Compress
gzip dj-system-backup.img
```

## 🎯 Performance Tips

- **Use Class 10 or A1-rated SD cards** for best performance
- **Keep SD card <80% full** to maintain speed
- **Clean up old songs** periodically
- **Use cooling fan** to prevent thermal throttling
- **Close unused applications** on Pi
- **Monitor CPU temperature**: `vcgencmd measure_temp`

## 📝 Default Settings

- **WiFi SSID**: DJ-Requests
- **WiFi Password**: DJParty2024
- **WiFi IP**: 192.168.4.1
- **Web Port**: 3000
- **Audio API Port**: 5001
- **Music Directory**: `/home/pi/dj-request-system/Music/`
- **Database**: `/home/pi/dj-request-system/data/requests.db`

## 🆘 Support

For issues:
1. Check logs: `journalctl -u dj-request.service -f`
2. Run status check: `./status.sh`
3. Test audio: `./test-audio.sh`
4. Check GitHub issues

## 📜 License

MIT License - feel free to modify and use for your events!

## 🙏 Credits

Built with:
- Node.js / Express
- SQLite
- Socket.io
- yt-dlp
- mpv
- Focusrite Scarlett USB Audio

---

**Ready to DJ? Just plug in and go! 🎵**
