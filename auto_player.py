#!/usr/bin/env python3
"""
DJ Auto Player - Clean Audio, No Filters
Plays raw audio directly to hardware
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
PRELOAD_COUNT = 3

# Player state
class PlayerState:
    def __init__(self):
        self.current_song = None
        self.current_process = None
        self.is_playing = False
        self.is_paused = False
        self.position = 0
        self.duration = 0
        self.volume = 100
        self.skip_requested = False
        self.lock = Lock()
        
    def to_dict(self):
        with self.lock:
            return {
                'current_song': self.current_song,
                'is_playing': self.is_playing,
                'is_paused': self.is_paused,
                'position': self.position,
                'duration': self.duration,
                'volume': self.volume
            }

player_state = PlayerState()
stop_event = Event()
download_lock = Lock()

print("🎵 DJ Auto Player Starting...")
print(f"📁 Database: {DB_PATH}")
print(f"🎵 Music folder: {MUSIC_LIBRARY}")
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
                for file in Path(MUSIC_LIBRARY).glob(f"*{pattern}*{ext}"):
                    return str(file.absolute())
        return None
    except:
        return None

def download_from_youtube(song_id, title, artist):
    """Download song from YouTube with smart search"""
    try:
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        if os.path.exists(output_path):
            print(f"✅ Already have: {safe_title}")
            return output_path
        
        # If song_id looks like a YouTube video ID, use direct URL
        if song_id and len(song_id) == 11:
            url = f"https://www.youtube.com/watch?v={song_id}"
        else:
            search_query = f"{artist} {title} audio"
            url = f"ytsearch1:{search_query}"
        
        print(f"⬇️  Downloading: {safe_title}")
        
        # Filter out live/acoustic versions
        match_filter = "title!~=(?i)(live|acoustic|cover|karaoke|instrumental|concert|unplugged)"
        
        cmd = [
            'yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0',
            '-o', output_path, '--no-playlist', '--quiet',
            '--match-filter', match_filter, url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        
        # Fallback without filter
        cmd_fallback = [
            'yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0',
            '-o', output_path, '--no-playlist', '--quiet', url
        ]
        result = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded (fallback): {safe_title}")
            return output_path
            
        print(f"❌ Download failed")
        return None
        
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None

def get_audio_duration(file_path):
    """Get duration of audio file"""
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0

def play_song(file_path):
    """Play audio file - NO FILTERS, raw audio"""
    try:
        duration = get_audio_duration(file_path)
        
        with player_state.lock:
            player_state.duration = duration
            player_state.is_playing = True
            player_state.is_paused = False
            player_state.skip_requested = False
            player_state.position = 0
        
        print(f"▶️  Playing: {os.path.basename(file_path)}")
        
        # CLEAN PLAYBACK - NO AUDIO FILTERS
        cmd = ['ffplay', '-nodisp', '-autoexit', file_path]
        
        player_state.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE
        )
        
        start_time = time.time()
        
        while player_state.current_process.poll() is None:
            if stop_event.is_set():
                player_state.current_process.terminate()
                return 'stopped'
            
            # Check for skip
            with player_state.lock:
                if player_state.skip_requested:
                    player_state.skip_requested = False
                    player_state.current_process.terminate()
                    print("⏭️  Skipped")
                    return 'skipped'
                
                # Check for pause
                if player_state.is_paused:
                    player_state.current_process.terminate()
                    print("⏸️  Paused")
                    return 'paused'
            
            # Update position
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(elapsed, duration)
            
            time.sleep(0.25)
        
        with player_state.lock:
            player_state.is_playing = False
            player_state.position = 0
        
        return 'completed'
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        with player_state.lock:
            player_state.is_playing = False
        return 'error'

def preload_queue():
    """Background thread to pre-download upcoming songs"""
    print("📥 Pre-download service started")
    
    while not stop_event.is_set():
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, song_id, title, artist FROM queue 
                WHERE played = 0 ORDER BY requested_at ASC LIMIT ?
            """, (PRELOAD_COUNT,))
            songs = cursor.fetchall()
            conn.close()
            
            for queue_id, song_id, title, artist in songs:
                if stop_event.is_set():
                    break
                file_path = search_song_in_library(song_id, title, artist)
                if not file_path:
                    with download_lock:
                        download_from_youtube(song_id, title, artist)
            
            time.sleep(10)
        except Exception as e:
            time.sleep(10)

def mark_song_played(queue_id, song_id, title, artist):
    """Mark song as played in database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE queue SET played = 1 WHERE id = ?", (queue_id,))
        cursor.execute(
            "INSERT INTO recently_played (song_id, title, artist) VALUES (?, ?, ?)",
            (song_id, title, artist)
        )
        conn.commit()
        conn.close()
        print(f"✅ Marked played: {title}")
    except Exception as e:
        print(f"⚠️  Mark played error: {e}")

def play_queue():
    """Main playback loop"""
    print("👀 Playback loop started")
    
    while not stop_event.is_set():
        try:
            # Check if paused
            with player_state.lock:
                if player_state.is_paused:
                    time.sleep(0.5)
                    continue
            
            # Get next song from queue
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, song_id, title, artist FROM queue 
                WHERE played = 0 ORDER BY requested_at ASC LIMIT 1
            """)
            song = cursor.fetchone()
            conn.close()
            
            if song:
                queue_id, song_id, title, artist = song
                
                with player_state.lock:
                    player_state.current_song = {
                        'id': queue_id,
                        'title': title,
                        'artist': artist
                    }
                
                # Find or download the song
                file_path = search_song_in_library(song_id, title, artist)
                if not file_path:
                    with download_lock:
                        file_path = download_from_youtube(song_id, title, artist)
                
                if file_path:
                    result = play_song(file_path)
                    
                    if result in ['completed', 'skipped']:
                        mark_song_played(queue_id, song_id, title, artist)
                    elif result == 'paused':
                        continue  # Don't mark as played
                else:
                    print(f"❌ Could not get: {title}")
                    mark_song_played(queue_id, song_id, title, artist)
            else:
                # No songs in queue
                with player_state.lock:
                    player_state.current_song = None
                    player_state.is_playing = False
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Queue error: {e}")
            time.sleep(5)

class ControlHandler(BaseHTTPRequestHandler):
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
        
        response = {'success': True}
        
        if self.path == '/skip':
            with player_state.lock:
                player_state.skip_requested = True
                player_state.is_paused = False
            print("⏭️  Skip requested")
            
        elif self.path == '/pause':
            with player_state.lock:
                player_state.is_paused = True
            print("⏸️  Pause requested")
            
        elif self.path == '/resume':
            with player_state.lock:
                player_state.is_paused = False
            print("▶️  Resume requested")
            
        elif self.path == '/volume':
            vol = data.get('volume', 100)
            with player_state.lock:
                player_state.volume = max(0, min(100, vol))
            response['volume'] = player_state.volume
            print(f"🔊 Volume: {player_state.volume}%")
        else:
            self.send_response(404)
            self.end_headers()
            return
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def start_control_server():
    # Bind to 0.0.0.0 so it's accessible from other machines!
    server = HTTPServer(('0.0.0.0', CONTROL_PORT), ControlHandler)
    print(f"🌐 Control server on port {CONTROL_PORT} (all interfaces)")
    server.serve_forever()

if __name__ == '__main__':
    print("=" * 50)
    print("🎵 DJ Auto Player - Clean Audio")
    print("=" * 50)
    print("✅ NO audio filters - raw playback")
    print("✅ Controls accessible from network")
    print("=" * 50)
    
    # Check dependencies
    for cmd in ['yt-dlp', 'ffplay', 'ffprobe']:
        try:
            subprocess.run([cmd, '--help'], capture_output=True, timeout=5)
            print(f"✅ {cmd} found")
        except:
            print(f"❌ {cmd} not found!")
            sys.exit(1)
    
    # Wait for database
    while not os.path.exists(DB_PATH):
        print("⏳ Waiting for database...")
        time.sleep(2)
    print("✅ Database ready")
    
    # Start threads
    Thread(target=preload_queue, daemon=True).start()
    Thread(target=play_queue, daemon=True).start()
    
    print("✅ Player running!")
    print()
    
    try:
        start_control_server()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        stop_event.set()
