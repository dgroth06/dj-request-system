#!/usr/bin/env python3
"""
DJ Auto Player - Direct ALSA output to Scarlett
Uses: ffmpeg | aplay -D hw:2,0 -f S32_LE -r 96000 -c 2
ZERO processing - raw 32-bit audio at 96kHz
"""

import os
import sys
import time
import sqlite3
import subprocess
import shlex
from pathlib import Path
from threading import Thread, Event, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Configuration
DB_PATH = 'dj_requests.db'
MUSIC_LIBRARY = 'Music'
CONTROL_PORT = 8888
PRELOAD_COUNT = 3

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

os.makedirs(MUSIC_LIBRARY, exist_ok=True)

def search_song_in_library(song_id, title, artist):
    try:
        safe_artist = "".join(c for c in artist if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        patterns = [f"{safe_artist} - {safe_title}", f"{safe_artist}-{safe_title}", safe_title, song_id]
        for pattern in patterns:
            for ext in ['.mp3', '.m4a', '.flac', '.wav']:
                for file in Path(MUSIC_LIBRARY).glob(f"*{pattern}*{ext}"):
                    return str(file.absolute())
        return None
    except:
        return None

def download_from_youtube(song_id, title, artist):
    try:
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        if os.path.exists(output_path):
            return output_path
        
        if song_id and len(song_id) == 11:
            url = f"https://www.youtube.com/watch?v={song_id}"
        else:
            url = f"ytsearch1:{artist} {title}"
        
        print(f"⬇️  Downloading: {safe_title}")
        
        cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0',
               '-o', output_path, '--no-playlist', '--quiet', url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        return None
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None

def get_audio_duration(file_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return 0

def play_song(file_path):
    """Play audio using ffmpeg | aplay - direct to Scarlett at 96kHz S32_LE"""
    try:
        duration = get_audio_duration(file_path)
        
        with player_state.lock:
            player_state.duration = duration
            player_state.is_playing = True
            player_state.is_paused = False
            player_state.skip_requested = False
            player_state.position = 0
        
        print(f"▶️  Playing: {os.path.basename(file_path)}")
        
        # Use shlex.quote to properly escape the file path for shell
        safe_path = shlex.quote(file_path)
        
        # THE EXACT COMMAND THAT WORKS:
        # ffmpeg -i "file" -f s32le -ar 96000 -ac 2 - 2>/dev/null | aplay -D hw:2,0 -f S32_LE -r 96000 -c 2
        cmd = f'ffmpeg -i {safe_path} -f s32le -ar 96000 -ac 2 - 2>/dev/null | aplay -D hw:2,0 -f S32_LE -r 96000 -c 2'
        
        player_state.current_process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        start_time = time.time()
        
        while player_state.current_process.poll() is None:
            if stop_event.is_set():
                player_state.current_process.terminate()
                subprocess.run(['pkill', '-f', 'aplay'], capture_output=True)
                subprocess.run(['pkill', '-f', 'ffmpeg'], capture_output=True)
                return 'stopped'
            
            with player_state.lock:
                if player_state.skip_requested:
                    player_state.skip_requested = False
                    player_state.current_process.terminate()
                    subprocess.run(['pkill', '-f', 'aplay'], capture_output=True)
                    subprocess.run(['pkill', '-f', 'ffmpeg'], capture_output=True)
                    return 'skipped'
                if player_state.is_paused:
                    player_state.current_process.terminate()
                    subprocess.run(['pkill', '-f', 'aplay'], capture_output=True)
                    subprocess.run(['pkill', '-f', 'ffmpeg'], capture_output=True)
                    return 'paused'
                player_state.position = time.time() - start_time
            
            time.sleep(0.25)
        
        with player_state.lock:
            player_state.is_playing = False
        return 'completed'
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        return 'error'

def preload_queue():
    while not stop_event.is_set():
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id, song_id, title, artist FROM queue WHERE played = 0 ORDER BY requested_at ASC LIMIT ?", (PRELOAD_COUNT,))
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
        except:
            time.sleep(10)

def mark_song_played(queue_id, song_id, title, artist):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE queue SET played = 1 WHERE id = ?", (queue_id,))
        cursor.execute("INSERT INTO recently_played (song_id, title, artist) VALUES (?, ?, ?)", (song_id, title, artist))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  DB error: {e}")

def play_queue():
    while not stop_event.is_set():
        try:
            with player_state.lock:
                if player_state.is_paused:
                    time.sleep(0.5)
                    continue
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id, song_id, title, artist FROM queue WHERE played = 0 ORDER BY requested_at ASC LIMIT 1")
            song = cursor.fetchone()
            conn.close()
            
            if song:
                queue_id, song_id, title, artist = song
                
                with player_state.lock:
                    player_state.current_song = {'id': queue_id, 'title': title, 'artist': artist}
                
                file_path = search_song_in_library(song_id, title, artist)
                if not file_path:
                    with download_lock:
                        file_path = download_from_youtube(song_id, title, artist)
                
                if file_path:
                    result = play_song(file_path)
                    if result in ['completed', 'skipped']:
                        mark_song_played(queue_id, song_id, title, artist)
                else:
                    print(f"❌ Could not find or download: {title}")
                    mark_song_played(queue_id, song_id, title, artist)
            else:
                with player_state.lock:
                    player_state.current_song = None
                    player_state.is_playing = False
                time.sleep(2)
        except Exception as e:
            print(f"❌ Error: {e}")
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
                
        elif self.path == '/pause':
            with player_state.lock:
                player_state.is_paused = True
                
        elif self.path == '/resume':
            with player_state.lock:
                player_state.is_paused = False
                
        elif self.path == '/volume':
            vol = data.get('volume', 100)
            with player_state.lock:
                player_state.volume = max(0, min(100, vol))
            response['volume'] = player_state.volume
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

if __name__ == '__main__':
    print("🎵 DJ Auto Player - Scarlett 96kHz S32_LE")
    print("=" * 45)
    print("✅ ffmpeg | aplay -D hw:2,0 -f S32_LE -r 96000")
    print("✅ Direct ALSA - no PipeWire")
    print("=" * 45)
    
    for cmd in ['yt-dlp', 'ffmpeg', 'ffprobe', 'aplay']:
        try:
            subprocess.run([cmd, '--help'], capture_output=True, timeout=5)
            print(f"✅ {cmd}")
        except:
            print(f"❌ {cmd} not found!")
            sys.exit(1)
    
    while not os.path.exists(DB_PATH):
        print("⏳ Waiting for database...")
        time.sleep(2)
    print("✅ Database ready")
    
    Thread(target=preload_queue, daemon=True).start()
    Thread(target=play_queue, daemon=True).start()
    print("✅ Player running")
    
    server = HTTPServer(('0.0.0.0', CONTROL_PORT), ControlHandler)
    print(f"🌐 Control server: port {CONTROL_PORT}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
        stop_event.set()
        subprocess.run(['pkill', '-f', 'aplay'], capture_output=True)
        subprocess.run(['pkill', '-f', 'ffmpeg'], capture_output=True)
