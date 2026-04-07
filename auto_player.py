#!/usr/bin/env python3
"""
Fully Automated DJ Player - No GUI Required
Pre-downloads queue to prevent dead time
Perfect for Raspberry Pi deployment
"""

import os
import sys
import time
import sqlite3
import subprocess
from pathlib import Path
from threading import Thread, Event, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Configuration
DB_PATH = 'dj_requests.db'
MUSIC_LIBRARY = 'Music'
CONTROL_PORT = 8888
CROSSFADE_DURATION = 10  # seconds
PRELOAD_COUNT = 3  # Number of songs to download ahead

# Audio player state
class PlayerState:
    def __init__(self):
        self.current_song = None
        self.current_process = None
        self.next_song = None
        self.queue = []
        self.is_playing = False
        self.position = 0
        self.duration = 0
        self.volume = 100
        self.paused_song = None
        self.paused_position = 0
        self.lock = Lock()
        
    def to_dict(self):
        with self.lock:
            return {
                'current_song': self.current_song,
                'is_playing': self.is_playing,
                'position': self.position,
                'duration': self.duration,
                'queue_length': len(self.queue),
                'volume': self.volume
            }

player_state = PlayerState()
stop_event = Event()
download_lock = Lock()

print(f"🎵 Automated DJ Player Starting...")
print(f"📁 Database: {DB_PATH}")
print(f"🎵 Music folder: {MUSIC_LIBRARY}")
print(f"🔀 Crossfade: {CROSSFADE_DURATION} seconds")
print(f"📥 Pre-download: {PRELOAD_COUNT} songs ahead")
print()

os.makedirs(MUSIC_LIBRARY, exist_ok=True)

def search_song_in_library(song_id, title, artist):
    """Search for song file in music library"""
    try:
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        
        patterns = [
            f"{safe_artist} - {safe_title}",
            f"{safe_artist}-{safe_title}",
            safe_title,
            song_id
        ]
        
        for pattern in patterns:
            for ext in ['.mp3', '.m4a', '.flac', '.wav']:
                search_path = Path(MUSIC_LIBRARY)
                for file in search_path.glob(f"*{pattern}*{ext}"):
                    return str(file.absolute())
        
        return None
    except Exception as e:
        return None

def download_from_youtube(song_id, title, artist):
    """Download song from YouTube with smart search to avoid live/acoustic versions"""
    try:
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        if os.path.exists(output_path):
            print(f"✅ Already have: {safe_title}")
            return output_path
        
        # If song_id looks like a YouTube video ID (11 chars), use direct URL
        # Otherwise, use smart search
        if song_id and len(song_id) == 11 and song_id.isalnum():
            url = f"https://www.youtube.com/watch?v={song_id}"
        else:
            # Smart search: prefer radio/album versions, exclude live/acoustic
            # Build search query with exclusions
            search_query = f"{artist} {title} audio"
            url = f"ytsearch1:{search_query}"
        
        print(f"⬇️  Downloading: {safe_title}")
        
        # yt-dlp match filter to reject unwanted versions
        # This filters OUT videos with these terms in the title
        match_filter = "title!~=(?i)(live|acoustic|cover|karaoke|instrumental|tribute|performance|concert|unplugged|demo|session|slowed|sped.up|speed.up|8d.audio|music.video|official.video)"
        
        cmd = [
            'yt-dlp',
            '-x',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '-o', output_path,
            '--no-playlist',
            '--quiet',
            '--match-filter', match_filter,
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        else:
            # Fallback: try without match filter (in case it filtered everything)
            print(f"⚠️  Retrying without filter...")
            cmd_fallback = [
                'yt-dlp',
                '-x',
                '--audio-format', 'mp3',
                '--audio-quality', '0',
                '-o', output_path,
                '--no-playlist',
                '--quiet',
                url
            ]
            result = subprocess.run(cmd_fallback, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"✅ Downloaded (fallback): {safe_title}")
                return output_path
            
            print(f"❌ Download failed")
            return None
        
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None

def get_audio_duration(file_path):
    """Get duration of audio file in seconds"""
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 
               'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0

def play_with_crossfade(current_file, next_file=None):
    """Play audio file with crossfade to next if available"""
    try:
        duration = get_audio_duration(current_file)
        player_state.duration = duration
        player_state.is_playing = True
        
        print(f"▶️  Playing: {os.path.basename(current_file)}")
        
        # Build ffplay command with volume control
        volume_filter = f"volume={player_state.volume / 100}"
        
        if next_file and os.path.exists(next_file):
            # Play with crossfade using ffmpeg
            fade_start = max(0, duration - CROSSFADE_DURATION)
            
            cmd = [
                'ffplay',
                '-nodisp',
                '-autoexit',
                '-af', f'{volume_filter},afade=t=out:st={fade_start}:d={CROSSFADE_DURATION}',
                current_file
            ]
        else:
            # Play normally with volume
            cmd = ['ffplay', '-nodisp', '-autoexit', '-af', volume_filter, current_file]
        
        # Start playback
        player_state.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE
        )
        
        # Wait for playback to finish or be interrupted
        start_time = time.time()
        while player_state.current_process and player_state.current_process.poll() is None:
            if stop_event.is_set():
                player_state.current_process.terminate()
                break
            
            # Update position
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(elapsed, duration)
            
            time.sleep(0.5)
        
        player_state.is_playing = False
        player_state.position = 0
        
        return True
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        player_state.is_playing = False
        return False

def preload_queue():
    """Background thread to pre-download upcoming songs"""
    print("📥 Starting pre-download service...")
    
    while not stop_event.is_set():
        try:
            # Get next songs in queue
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, song_id, title, artist 
                FROM queue 
                WHERE played = 0 
                ORDER BY requested_at ASC
                LIMIT ?
            """, (PRELOAD_COUNT,))
            songs = cursor.fetchall()
            conn.close()
            
            # Download any missing songs
            for queue_id, song_id, title, artist in songs:
                if stop_event.is_set():
                    break
                
                # Check if we already have it
                file_path = search_song_in_library(song_id, title, artist)
                
                if not file_path:
                    with download_lock:
                        print(f"📥 Pre-downloading: {title} by {artist}")
                        file_path = download_from_youtube(song_id, title, artist)
                        if file_path:
                            print(f"✅ Ready: {title}")
            
            # Sleep before checking again
            time.sleep(10)
            
        except Exception as e:
            print(f"⚠️  Pre-download error: {e}")
            time.sleep(10)

def mark_song_played(queue_id):
    """Mark song as played in database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM queue WHERE id = ?", (queue_id,))
        song = cursor.fetchone()
        
        if song:
            cursor.execute("UPDATE queue SET played = 1 WHERE id = ?", (queue_id,))
            cursor.execute(
                "INSERT INTO recently_played (song_id, title, artist) VALUES (?, ?, ?)",
                (song[1], song[2], song[3])
            )
            conn.commit()
            print(f"✅ Marked as played: {song[2]}")
        
        conn.close()
    except Exception as e:
        print(f"❌ Mark played error: {e}")

def set_volume(volume):
    """Set playback volume (0-100)"""
    with player_state.lock:
        player_state.volume = max(0, min(100, volume))
    print(f"🔊 Volume: {player_state.volume}%")
def play_queue():
    """Main playback loop - plays queue with crossfading"""
    print("👀 Starting playback loop...")
    
    while not stop_event.is_set():
        try:
            # Get current queue from database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, song_id, title, artist 
                FROM queue 
                WHERE played = 0 
                ORDER BY requested_at ASC
                LIMIT 2
            """)
            songs = cursor.fetchall()
            conn.close()
            
            if not songs:
                # Queue is empty
                with player_state.lock:
                    player_state.current_song = None
                    player_state.is_playing = False
                time.sleep(5)
                continue
            
            current = songs[0]
            next_song = songs[1] if len(songs) > 1 else None
            
            queue_id, song_id, title, artist = current
            
            # Check if we have the file (should be pre-downloaded)
            file_path = search_song_in_library(song_id, title, artist)
            
            # Download if somehow not ready
            if not file_path:
                print(f"⚠️  Not pre-downloaded, downloading now: {title}")
                with download_lock:
                    file_path = download_from_youtube(song_id, title, artist)
            
            if not file_path:
                print(f"❌ Could not get: {title}")
                mark_song_played(queue_id)
                continue
            
            # Get next file if available
            next_file = None
            if next_song:
                next_id, next_song_id, next_title, next_artist = next_song
                next_file = search_song_in_library(next_song_id, next_title, next_artist)
            
            # Play with crossfade
            with player_state.lock:
                player_state.current_song = {'id': queue_id, 'title': title, 'artist': artist}
                player_state.next_song = next_file
            
            play_with_crossfade(file_path, next_file)
            
            # Mark as played
            mark_song_played(queue_id)
            
        except Exception as e:
            print(f"❌ Playback loop error: {e}")
            time.sleep(5)

class ControlHandler(BaseHTTPRequestHandler):
    """HTTP handler for control commands"""
    
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(player_state.to_dict()).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}
        
        if self.path == '/skip':
            # Skip current song
            if player_state.current_process:
                player_state.current_process.terminate()
                print("⏭️  Skipped by admin")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif self.path == '/pause':
            # Pause playback - kill current process
            if player_state.current_process:
                try:
                    player_state.current_process.terminate()
                    player_state.current_process.wait()
                    with player_state.lock:
                        player_state.is_playing = False
                        player_state.paused_song = player_state.current_song
                        player_state.paused_position = player_state.position
                    print("⏸️  Paused")
                except Exception as e:
                    print(f"⚠️  Pause error: {e}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif self.path == '/resume':
            # Resume playback - note: will restart current song
            # True pause/resume requires more complex state management
            with player_state.lock:
                player_state.is_playing = True
            print("▶️  Resumed (will continue with queue)")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
            
        elif self.path == '/volume':
            # Set volume - requires restarting playback with new volume
            volume = data.get('volume', 100)
            old_volume = player_state.volume
            set_volume(volume)
            
            # If currently playing, restart with new volume
            if player_state.current_process and player_state.volume != old_volume:
                try:
                    # Kill current playback
                    player_state.current_process.terminate()
                    player_state.current_process.wait()
                    print(f"🔄 Restarting playback with new volume: {player_state.volume}%")
                    # The playback loop will restart automatically with new volume
                except Exception as e:
                    print(f"⚠️  Volume change error: {e}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'volume': player_state.volume}).encode())
            
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def start_control_server():
    """Start HTTP control server"""
    server = HTTPServer(('localhost', CONTROL_PORT), ControlHandler)
    print(f"🌐 Control server on port {CONTROL_PORT}")
    server.serve_forever()

if __name__ == '__main__':
    print("=" * 60)
    print("🎵 Fully Automated DJ Player")
    print("=" * 60)
    print()
    print("✅ No GUI required - runs completely headless")
    print("✅ Auto-downloads songs from queue")
    print("✅ Professional crossfading (10 seconds)")
    print("✅ Perfect for Raspberry Pi")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    # Check dependencies
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
        print("✅ yt-dlp found")
    except:
        print("❌ ERROR: yt-dlp not found! Install: pip install yt-dlp")
        sys.exit(1)
    
    try:
        subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
        print("✅ ffmpeg/ffplay found")
    except:
        print("❌ ERROR: ffmpeg not found! Install: sudo apt install ffmpeg")
        sys.exit(1)
    
    # Wait for database
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Waiting for database...")
        while not os.path.exists(DB_PATH):
            time.sleep(2)
    print("✅ Database ready")
    print()
    
    # Start pre-download thread
    preload_thread = Thread(target=preload_queue, daemon=True)
    preload_thread.start()
    print("✅ Pre-download service started")
    
    # Start playback thread
    playback_thread = Thread(target=play_queue, daemon=True)
    playback_thread.start()
    print("✅ Playback engine started")
    print()
    
    # Start control server
    try:
        start_control_server()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        stop_event.set()
        if player_state.current_process:
            player_state.current_process.terminate()
        print("✅ Goodbye!")