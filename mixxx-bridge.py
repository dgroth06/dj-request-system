#!/usr/bin/env python3
"""
Mixxx Control Bridge - Fully Automated
No manual Mixxx interaction needed - completely self-reliant
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
from pathlib import Path
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
import signal

# Auto-detect platform
if sys.platform == "win32":
    DB_PATH = 'dj_requests.db'
    MUSIC_LIBRARY = 'Music'
    MIXXX_PLAYLIST = str(Path.home() / 'AppData' / 'Local' / 'Mixxx' / 'playlists' / 'dj_queue.m3u')
    MIXXX_CONFIG = str(Path.home() / 'AppData' / 'Local' / 'Mixxx' / 'mixxx.cfg')
elif sys.platform == "darwin":
    DB_PATH = 'dj_requests.db'
    MUSIC_LIBRARY = 'Music'
    MIXXX_PLAYLIST = str(Path.home() / 'Library' / 'Application Support' / 'Mixxx' / 'playlists' / 'dj_queue.m3u')
    MIXXX_CONFIG = str(Path.home() / 'Library' / 'Application Support' / 'Mixxx' / 'mixxx.cfg')
else:
    DB_PATH = 'dj_requests.db'
    MUSIC_LIBRARY = 'Music'
    MIXXX_PLAYLIST = str(Path.home() / '.mixxx' / 'playlists' / 'dj_queue.m3u')
    MIXXX_CONFIG = str(Path.home() / '.mixxx' / 'mixxx.cfg')

CONTROL_PORT = 8888
MIXXX_PROCESS = None

print(f"🖥️  Platform: {sys.platform}")
print(f"📁 Database: {DB_PATH}")
print(f"🎵 Music folder: {MUSIC_LIBRARY}")
print(f"📝 Mixxx playlist: {MIXXX_PLAYLIST}")
print()

os.makedirs(MUSIC_LIBRARY, exist_ok=True)
os.makedirs(os.path.dirname(MIXXX_PLAYLIST), exist_ok=True)

def monitor_queue():
    """Monitor the queue and auto-download new songs"""
    print("👀 Watching queue for new songs...")
    processed_songs = set()
    
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, song_id, title, artist 
                FROM queue 
                WHERE played = 0 
                ORDER BY requested_at ASC
            """)
            queue = cursor.fetchall()
            conn.close()
            
            if queue:
                for queue_id, song_id, title, artist in queue:
                    song_key = f"{song_id}_{queue_id}"
                    
                    if song_key not in processed_songs:
                        print(f"\n🆕 New request: {title} by {artist}")
                        
                        # Check if we have it
                        file_path = search_song_in_library(song_id, title, artist)
                        
                        if not file_path:
                            print(f"⬇️  Downloading...")
                            file_path = download_from_youtube(song_id, title, artist)
                        else:
                            print(f"✅ Already have it!")
                        
                        processed_songs.add(song_key)
                
                # Update Mixxx playlist
                update_mixxx_playlist()
            
            # Clean up processed songs that are no longer in queue
            processed_songs = {s for s in processed_songs if any(f"{q[1]}_{q[0]}" == s for q in queue)}
            
        except Exception as e:
            print(f"❌ Monitor error: {e}")
        
        time.sleep(5)  # Check every 5 seconds

def configure_mixxx_headless():
    """Configure Mixxx for fully automated headless operation"""
    print("⚙️  Configuring Mixxx for headless operation...")
    
    config_dir = os.path.dirname(MIXXX_CONFIG)
    os.makedirs(config_dir, exist_ok=True)
    
    # Create/update Mixxx configuration for auto-DJ
    config = f"""[Master]
num_decks=2
headphones_delay=0

[Library]
RescanOnStartup=1
Directory={os.path.abspath(MUSIC_LIBRARY)}

[AutoDJ]
EnableAutoDJ=1
Transition=0
TransitionTime=10000
MinimumAvailable=5
RandomQueue=0
UseIgnoreTime=0
RequeueOnEmpty=1

[Sound]
Master=1

[Playlist]
Directory={os.path.dirname(MIXXX_PLAYLIST)}
"""
    
    try:
        # Backup existing config if it exists
        if os.path.exists(MIXXX_CONFIG):
            backup = MIXXX_CONFIG + '.backup'
            if not os.path.exists(backup):
                with open(MIXXX_CONFIG, 'r') as f:
                    content = f.read()
                with open(backup, 'w') as f:
                    f.write(content)
        
        # Write new config
        with open(MIXXX_CONFIG, 'w') as f:
            f.write(config)
        
        print("✅ Mixxx configured for headless Auto-DJ")
        return True
    except Exception as e:
        print(f"⚠️  Config write failed: {e}")
        return False

def start_mixxx_headless():
    """Start Mixxx in headless mode with Auto-DJ enabled"""
    global MIXXX_PROCESS
    
    try:
        print("🎛️  Starting Mixxx in headless mode...")
        
        # Mixxx command line arguments for headless operation
        if sys.platform == "win32":
            mixxx_cmd = ['mixxx', '--resourcePath', os.path.abspath(MUSIC_LIBRARY)]
        else:
            mixxx_cmd = ['mixxx', '--resourcePath', os.path.abspath(MUSIC_LIBRARY)]
        
        # Start Mixxx as background process
        MIXXX_PROCESS = subprocess.Popen(
            mixxx_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE
        )
        
        print(f"✅ Mixxx started (PID: {MIXXX_PROCESS.pid})")
        
        # Wait a bit for Mixxx to initialize
        time.sleep(5)
        
        # Auto-load the playlist
        auto_load_playlist()
        
        return True
    except Exception as e:
        print(f"❌ Failed to start Mixxx: {e}")
        print("   Make sure Mixxx is installed!")
        return False

def auto_load_playlist():
    """Automatically load and start the Auto-DJ playlist"""
    try:
        # Create initial playlist if it doesn't exist
        if not os.path.exists(MIXXX_PLAYLIST):
            with open(MIXXX_PLAYLIST, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
        
        print("📋 Auto-DJ playlist initialized")
        
        # Update playlist with current queue
        update_mixxx_playlist()
        
    except Exception as e:
        print(f"⚠️  Playlist auto-load error: {e}")

def search_song_in_library(song_id, title, artist):
    """Search for song file in the music library"""
    try:
        # Clean search terms
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        
        # Search patterns
        patterns = [
            f"{safe_artist} - {safe_title}",
            f"{safe_artist}-{safe_title}",
            safe_title,
            song_id
        ]
        
        for pattern in patterns:
            for ext in ['.mp3', '.m4a', '.flac', '.wav']:
                search_path = Path(MUSIC_LIBRARY)
                # Case-insensitive search
                for file in search_path.glob(f"*{pattern}*{ext}"):
                    return str(file.absolute())
                for file in search_path.glob(f"*{pattern.lower()}*{ext}"):
                    return str(file.absolute())
        
        return None
    except Exception as e:
        print(f"Search error: {e}")
        return None

def download_from_youtube(song_id, title, artist):
    """
    Download song from YouTube using yt-dlp
    """
    try:
        # Clean filename
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        # Check if already downloaded
        if os.path.exists(output_path):
            print(f"✅ Already have: {safe_title}")
            return output_path
        
        # Download using yt-dlp
        url = f"https://www.youtube.com/watch?v={song_id}"
        
        print(f"⬇️ Downloading: {safe_title}")
        
        cmd = [
            'yt-dlp',
            '-x',  # Extract audio
            '--audio-format', 'mp3',
            '--audio-quality', '0',  # Best quality
            '-o', output_path,
            '--no-playlist',
            '--quiet',
            '--progress',
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        else:
            print(f"❌ Download failed: {result.stderr}")
            return None
        
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None

def update_mixxx_playlist():
    """Update Mixxx playlist with current queue - no duplicates"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, song_id, title, artist, duration 
            FROM queue 
            WHERE played = 0 
            ORDER BY requested_at ASC
        """)
        queue = cursor.fetchall()
        conn.close()
        
        if not queue:
            # Queue is empty, write empty playlist
            with open(MIXXX_PLAYLIST, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
            return 0
        
        # Get existing playlist to avoid duplicates
        existing_songs = set()
        if os.path.exists(MIXXX_PLAYLIST):
            try:
                with open(MIXXX_PLAYLIST, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            existing_songs.add(line)
            except:
                pass
        
        playlist_lines = []
        new_songs_added = 0
        
        for queue_id, song_id, title, artist, duration in queue:
            # Check if already downloaded
            file_path = search_song_in_library(song_id, title, artist)
            
            if file_path and os.path.exists(file_path):
                # Use absolute path for Mixxx
                abs_path = os.path.abspath(file_path)
                
                # Only add if not already in playlist
                if abs_path not in existing_songs:
                    playlist_lines.append(abs_path)
                    existing_songs.add(abs_path)
                    new_songs_added += 1
                    print(f"📝 Added to playlist: {title} by {artist}")
                else:
                    print(f"⏭️  Already in playlist: {title}")
        
        # Only rewrite playlist if we have new songs
        if new_songs_added > 0:
            # Write M3U playlist with all songs (existing + new)
            with open(MIXXX_PLAYLIST, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for path in existing_songs:
                    f.write(f"{path}\n")
            
            print(f"✅ Playlist updated: {new_songs_added} new track(s) added, {len(existing_songs)} total")
        
        return len(existing_songs)
        
    except Exception as e:
        print(f"❌ Playlist update error: {e}")
        return 0

def mark_song_played(queue_id):
    """Mark a song as played in the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get song details
        cursor.execute("SELECT * FROM queue WHERE id = ?", (queue_id,))
        song = cursor.fetchone()
        
        if song:
            # Mark as played
            cursor.execute("UPDATE queue SET played = 1 WHERE id = ?", (queue_id,))
            
            # Add to recently played
            cursor.execute("""
                INSERT INTO recently_played (song_id, title, artist)
                VALUES (?, ?, ?)
            """, (song[1], song[2], song[3]))
            
            conn.commit()
            print(f"Marked as played: {song[2]} by {song[3]}")
        
        conn.close()
    except Exception as e:
        print(f"Error marking song played: {e}")

class ControlHandler(BaseHTTPRequestHandler):
    """HTTP handler for control commands from Node.js"""
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)
        
        command = data.get('command')
        
        if command == 'skip':
            # Skip current track
            self.skip_track()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif command == 'speed_up':
            # Increase playback speed
            speed = data.get('speed', 1.25)
            self.set_playback_speed(speed)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif command == 'update_playlist':
            # Refresh the playlist
            update_mixxx_playlist()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif command == 'mark_played':
            queue_id = data.get('queue_id')
            mark_song_played(queue_id)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success": true}')
    
    def do_GET(self):
        """Return current status"""
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status.to_dict()).encode())
    
    def skip_track(self):
        """Skip to next track - implement Mixxx control here"""
        print("Skipping track...")
        # This would send MIDI/OSC command to Mixxx
        # For now, just update status
        pass
    
    def set_playback_speed(self, speed):
        """Change playback speed"""
        print(f"Setting playback speed to {speed}x")
        # This would send MIDI/OSC command to Mixxx
        pass
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def monitor_mixxx():
    """Monitor Mixxx playback status"""
    while True:
        try:
            # In production, read from Mixxx's control objects
            # For now, simulate playback
            if status.playing:
                status.position += 1
                if status.position >= status.duration:
                    # Song finished, load next
                    status.position = 0
                    update_mixxx_playlist()
            
            status.save()
            
        except Exception as e:
            print(f"Monitor error: {e}")
        
        time.sleep(1)

def start_control_server():
    """Start HTTP server for control commands"""
    server = HTTPServer(('localhost', CONTROL_PORT), ControlHandler)
    print(f"Control server listening on port {CONTROL_PORT}")
    server.serve_forever()

if __name__ == '__main__':
    print("=" * 60)
    print("🎵 Mixxx Control Bridge - Fully Automated Mode")
    print("=" * 60)
    print()
    print("This script will:")
    print("  • Configure Mixxx for headless Auto-DJ")
    print("  • Start Mixxx automatically")
    print("  • Watch queue and auto-download songs")
    print("  • Auto-play with crossfading (10 seconds)")
    print("  • Run completely hands-free")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    # Check dependencies
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        print(f"✅ yt-dlp found: {result.stdout.strip()}")
    except FileNotFoundError:
        print("❌ ERROR: yt-dlp not found!")
        print("   Install: pip install yt-dlp")
        sys.exit(1)
    
    # Wait for database
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Waiting for database: {DB_PATH}")
        while not os.path.exists(DB_PATH):
            time.sleep(2)
    print("✅ Database found")
    print()
    
    # Configure Mixxx
    configure_mixxx_headless()
    
    # Start Mixxx in headless mode
    # Note: On Raspberry Pi with no display, skip GUI start
    if os.environ.get('DISPLAY') and sys.platform != "win32":
        start_mixxx_headless()
    else:
        print("ℹ️  Running in headless mode (no Mixxx GUI)")
        print("   Files will be prepared for Mixxx to play")
    
    print()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutting down...")
        if MIXXX_PROCESS:
            print("   Stopping Mixxx...")
            MIXXX_PROCESS.terminate()
            MIXXX_PROCESS.wait()
        print("✅ Goodbye!")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start queue monitor
    monitor_thread = Thread(target=monitor_queue, daemon=True)
    monitor_thread.start()
    
    # Start control server
    try:
        start_control_server()
    except KeyboardInterrupt:
        signal_handler(None, None)