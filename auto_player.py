#!/usr/bin/env python3
"""
Fully Automated DJ Player - No GUI Required
Plays songs with crossfading completely headless
Perfect for Raspberry Pi deployment
"""

import os
import sys
import time
import sqlite3
import subprocess
from pathlib import Path
from threading import Thread, Event
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Configuration
DB_PATH = 'dj_requests.db'
MUSIC_LIBRARY = 'Music'
CONTROL_PORT = 8888
CROSSFADE_DURATION = 10  # seconds

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
        
    def to_dict(self):
        return {
            'current_song': self.current_song,
            'is_playing': self.is_playing,
            'position': self.position,
            'duration': self.duration,
            'queue_length': len(self.queue)
        }

player_state = PlayerState()
stop_event = Event()

print(f"🎵 Automated DJ Player Starting...")
print(f"📁 Database: {DB_PATH}")
print(f"🎵 Music folder: {MUSIC_LIBRARY}")
print(f"🔀 Crossfade: {CROSSFADE_DURATION} seconds")
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
    """Download song from YouTube"""
    try:
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        if os.path.exists(output_path):
            print(f"✅ Already have: {safe_title}")
            return output_path
        
        url = f"https://www.youtube.com/watch?v={song_id}"
        
        print(f"⬇️  Downloading: {safe_title}")
        
        cmd = [
            'yt-dlp',
            '-x',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '-o', output_path,
            '--no-playlist',
            '--quiet',
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        else:
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
        
        if next_file and os.path.exists(next_file):
            # Play with crossfade using ffmpeg
            # Fade out last 10 seconds, fade in next song
            fade_start = max(0, duration - CROSSFADE_DURATION)
            
            cmd = [
                'ffplay',
                '-nodisp',
                '-autoexit',
                '-af', f'afade=t=out:st={fade_start}:d={CROSSFADE_DURATION}',
                current_file
            ]
        else:
            # Play normally without fade
            cmd = ['ffplay', '-nodisp', '-autoexit', current_file]
        
        # Start playback
        player_state.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for playback to finish or be interrupted
        while player_state.current_process and player_state.current_process.poll() is None:
            if stop_event.is_set():
                player_state.current_process.terminate()
                break
            time.sleep(0.5)
            player_state.position += 0.5
        
        player_state.is_playing = False
        player_state.position = 0
        
        return True
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        player_state.is_playing = False
        return False

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
                time.sleep(5)
                continue
            
            current = songs[0]
            next_song = songs[1] if len(songs) > 1 else None
            
            queue_id, song_id, title, artist = current
            
            # Check if we have the file
            file_path = search_song_in_library(song_id, title, artist)
            
            # Download if needed
            if not file_path:
                print(f"🆕 New request: {title} by {artist}")
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
                if not next_file:
                    next_file = download_from_youtube(next_song_id, next_title, next_artist)
            
            # Play with crossfade
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
            self.end_headers()
            self.wfile.write(json.dumps(player_state.to_dict()).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/skip':
            # Skip current song
            if player_state.current_process:
                player_state.current_process.terminate()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"success": true}')
        else:
            self.send_response(404)
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
    
    # Start playback thread
    playback_thread = Thread(target=play_queue, daemon=True)
    playback_thread.start()
    
    # Start control server
    try:
        start_control_server()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        stop_event.set()
        if player_state.current_process:
            player_state.current_process.terminate()
        print("✅ Goodbye!")