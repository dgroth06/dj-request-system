# 🚀 GitHub Deployment Guide

This guide will help you deploy the DJ Request System to your Raspberry Pi using GitHub.

## 📋 Prerequisites

- GitHub account
- Git installed on your development computer
- Raspberry Pi 5 with internet access (for initial setup)
- Focusrite Scarlett Solo/2i2 connected to Raspberry Pi

## 🌐 Setting Up GitHub Repository

### Option 1: Create New Repository on GitHub

1. Go to [GitHub](https://github.com) and sign in
2. Click the "+" icon → "New repository"
3. Name it: `dj-request-system`
4. Make it Public or Private
5. Don't initialize with README (we have one)
6. Click "Create repository"

### Option 2: Push to Existing Repository

On your development computer (where you have all the files):

```bash
# Navigate to where you have the files
cd /path/to/dj-request-system

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - DJ Request System"

# Add your GitHub repository as remote
git remote add origin https://github.com/YOUR_USERNAME/dj-request-system.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## 📁 Required Files Structure

Make sure your repository has these files:

```
dj-request-system/
├── install.sh              # Main installer script
├── github-install.sh       # Quick GitHub installer
├── server.js              # Node.js server
├── audio_player.py        # Python audio player
├── package.json           # Node.js dependencies
├── README.md              # Documentation
├── public/
│   ├── index.html        # User request page
│   └── admin.html        # DJ admin panel
└── .gitignore            # Git ignore file
```

### Create .gitignore

Create a `.gitignore` file to exclude unnecessary files:

```
# Dependencies
node_modules/

# Database
data/
*.db

# Music files
Music/

# Logs
*.log
npm-debug.log*

# OS files
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
```

## 🔧 One-Command Install on Raspberry Pi

### Method 1: Quick Install Script

On your Raspberry Pi, run:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/dj-request-system/main/github-install.sh | bash
```

This will:
1. Clone your repository
2. Run the installer
3. Set everything up automatically

### Method 2: Manual Install

```bash
# Install Git (if not already installed)
sudo apt install -y git

# Clone your repository
cd ~
git clone https://github.com/YOUR_USERNAME/dj-request-system.git
cd dj-request-system

# Make installer executable
chmod +x install.sh

# Run installer
./install.sh

# Reboot to activate WiFi access point
sudo reboot
```

## 📝 Post-Installation

After installation and reboot:

1. **Connect Hardware**:
   - Focusrite Scarlett plugged into USB
   - XLR cables connected to mixer

2. **Test System**:
   ```bash
   cd ~/dj-request-system
   ./test-audio.sh
   ./status.sh
   ```

3. **Connect to WiFi**:
   - Network: `DJ-Requests`
   - Password: `DJParty2024`

4. **Access Interfaces**:
   - User Requests: `http://192.168.4.1:3000`
   - Admin Panel: `http://192.168.4.1:3000/admin`

## 🔄 Updating from GitHub

To update your installation with the latest changes:

```bash
cd ~/dj-request-system

# Stop the service
sudo systemctl stop dj-request.service

# Pull latest changes
git pull origin main

# Install any new dependencies
npm install

# Restart service
sudo systemctl start dj-request.service

# Or reboot
sudo reboot
```

## 🌟 Making Changes

### On Your Development Computer

```bash
# Make changes to files
nano server.js  # or use your preferred editor

# Stage changes
git add .

# Commit changes
git commit -m "Description of changes"

# Push to GitHub
git push origin main
```

### On Raspberry Pi

```bash
# Pull changes
cd ~/dj-request-system
git pull origin main

# Restart
sudo systemctl restart dj-request.service
```

## 🔐 Private Repository Access

If your repository is private, you'll need to authenticate:

### Option 1: Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token with `repo` scope
3. On Raspberry Pi:
   ```bash
   git clone https://YOUR_TOKEN@github.com/YOUR_USERNAME/dj-request-system.git
   ```

### Option 2: SSH Key

1. Generate SSH key on Pi:
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   cat ~/.ssh/id_ed25519.pub
   ```

2. Add to GitHub → Settings → SSH and GPG keys

3. Clone with SSH:
   ```bash
   git clone git@github.com:YOUR_USERNAME/dj-request-system.git
   ```

## 📦 Creating Installation Package

To share your system or deploy to multiple Pis:

1. **Create a release on GitHub**:
   - Go to your repository → Releases → Create new release
   - Tag: `v1.0.0`
   - Title: `Initial Release`
   - Upload a zip of your files
   - Publish release

2. **Users can download**:
   ```bash
   wget https://github.com/YOUR_USERNAME/dj-request-system/archive/refs/tags/v1.0.0.zip
   unzip v1.0.0.zip
   cd dj-request-system-1.0.0
   ./install.sh
   ```

## ✅ Verification Checklist

After deployment, verify:

- [ ] System boots automatically
- [ ] WiFi access point is visible
- [ ] Can connect to `DJ-Requests` network
- [ ] Web interface loads at `http://192.168.4.1:3000`
- [ ] Admin panel accessible
- [ ] Focusrite Scarlett detected (`lsusb | grep -i focusrite`)
- [ ] Audio test works (`./test-audio.sh`)
- [ ] Can submit song requests
- [ ] Songs download successfully
- [ ] Audio plays through XLR outputs

## 🆘 Common Issues

### Repository Not Found
- Check URL is correct
- Verify repository is public (or you're authenticated)

### Permission Denied
- Use HTTPS instead of SSH if you don't have SSH keys set up
- Or set up SSH keys properly

### Installation Fails
- Check internet connection: `ping google.com`
- Update system first: `sudo apt update && sudo apt upgrade -y`
- Check disk space: `df -h`

## 📚 Resources

- [GitHub Documentation](https://docs.github.com)
- [Git Tutorial](https://git-scm.com/book/en/v2)
- [Raspberry Pi Forums](https://forums.raspberrypi.com)

---

**Happy DJing! 🎵**
