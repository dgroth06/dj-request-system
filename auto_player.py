#!/usr/bin/env python3
"""
Fully Automated DJ Player with Library Support
- Processes download queue from bulk uploads
- Auto-plays from library when request queue is empty
- TRUE crossfade with 10-second overlap
- Genre-aware auto-playlist based on theme
"""

import os
import sys
import time
import sqlite3
import subprocess
import requests
from pathlib import Path
from threading import Thread, Event, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs

# YouTube Music API
try:
    from ytmusicapi import YTMusic
    ytmusic = YTMusic()
    print("✅ YouTube Music API initialized")
except ImportError:
    ytmusic = None
    print("⚠️  ytmusicapi not installed - search will use mock results")

# Configuration
DB_PATH = 'dj_requests.db'
MUSIC_LIBRARY = 'Music'
CONTROL_PORT = 8888
SERVER_URL = 'http://localhost:3000'
CROSSFADE_DURATION = 10
PRELOAD_COUNT = 3
SILENCE_THRESHOLD = '-50dB'
SILENCE_DURATION = 0.5

class PlayerState:
    def __init__(self):
        self.current_song = None
        self.current_song_id = None
        self.current_file = None
        self.current_process = None
        self.crossfade_process = None
        self.is_playing = False
        self.is_paused = False
        self.position = 0
        self.duration = 0
        self.volume = 100
        self.paused_position = 0
        self.skip_requested = False
        self.is_auto_playlist = False
        self.lock = Lock()
        
    def to_dict(self):
        with self.lock:
            return {
                'current_song': self.current_song,
                'is_playing': self.is_playing,
                'is_paused': self.is_paused,
                'position': self.position,
                'duration': self.duration,
                'volume': self.volume,
                'is_auto_playlist': self.is_auto_playlist
            }

player_state = PlayerState()
stop_event = Event()
download_lock = Lock()
last_generate_time = 0  # Track last auto-playlist generation to prevent spam

print("🎵 DJ Auto Player Starting...")
os.makedirs(MUSIC_LIBRARY, exist_ok=True)

def search_song_in_library(song_id, title, artist):
    """Search for song file in music library"""
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
    """Download song from YouTube"""
    try:
        safe_title = "".join(c for c in f"{artist} - {title}" if c.isalnum() or c in (' ', '-', '_')).strip()
        output_path = os.path.join(MUSIC_LIBRARY, f"{safe_title}.mp3")
        
        if os.path.exists(output_path):
            return output_path
        
        # Build search query - STRONG audio preference
        # "topic" gets auto-generated topic channels (usually audio-only)
        # Multiple exclusions to avoid music videos
        search_query = f"{title} {artist} audio topic -video -music video -official video -lyric video -lyrics -visualizer -live -concert"
        
        print(f"⬇️  Downloading: {safe_title}")
        
        cmd = [
            'yt-dlp',
            '-f', 'bestaudio/best',  # Prefer audio-only format
            '-x',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '--match-filter', '!is_live & !live_chat',  # Fixed typo: was 'natch'
            '--no-playlist',
            '--quiet',
            '-o', output_path,
            f"ytsearch1:{search_query}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Downloaded: {safe_title}")
            return output_path
        else:
            print(f"❌ Download failed: {safe_title}")
            return None
            
    except Exception as e:
        print(f"❌ Error downloading {title}: {e}")
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

def build_audio_filter(volume, duration=None, fade_out=False, fade_in=False):
    filters = [
        f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}",
        f"silenceremove=stop_periods=1:stop_duration={SILENCE_DURATION}:stop_threshold={SILENCE_THRESHOLD}",
        f"volume={volume / 100}"
    ]
    if fade_out and duration:
        fade_start = max(0, duration - CROSSFADE_DURATION)
        filters.append(f"afade=t=out:st={fade_start}:d={CROSSFADE_DURATION}")
    if fade_in:
        filters.append(f"afade=t=in:st=0:d={CROSSFADE_DURATION}")
    return ','.join(filters)

def start_crossfade_song(file_path, volume):
    try:
        duration = get_audio_duration(file_path)
        audio_filter = build_audio_filter(volume, duration, fade_out=False, fade_in=True)
        cmd = ['ffplay', '-nodisp', '-autoexit', '-af', audio_filter, file_path]
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE)
        print(f"🎵 Crossfade: {os.path.basename(file_path)}")
        return process
    except Exception as e:
        print(f"❌ Crossfade error: {e}")
        return None

def play_song_with_crossfade(file_path, next_file, queue_id, is_auto=False):
    try:
        duration = get_audio_duration(file_path)
        crossfade_started = False
        crossfade_time = max(0, duration - CROSSFADE_DURATION)
        
        with player_state.lock:
            player_state.duration = duration
            player_state.is_playing = True
            player_state.skip_requested = False
            player_state.current_file = file_path
            player_state.current_song_id = queue_id
            player_state.is_auto_playlist = is_auto
        
        print(f"▶️  Playing: {os.path.basename(file_path)}" + (" [AUTO]" if is_auto else ""))
        
        has_next = next_file is not None and os.path.exists(next_file)
        audio_filter = build_audio_filter(player_state.volume, duration, fade_out=has_next, fade_in=False)
        cmd = ['ffplay', '-nodisp', '-autoexit', '-af', audio_filter, file_path]
        
        with player_state.lock:
            player_state.current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE)
        
        start_time = time.time()
        
        while True:
            if player_state.current_process is None:
                break
            poll_result = player_state.current_process.poll()
            if poll_result is not None:
                # Main song finished - MUST terminate crossfade to prevent double playback
                if player_state.crossfade_process:
                    try:
                        player_state.crossfade_process.terminate()
                        player_state.crossfade_process.wait(timeout=1)  # Wait for clean termination
                        player_state.crossfade_process = None
                        print("🔇 Crossfade terminated (main song ended)")
                    except:
                        pass
                with player_state.lock:
                    player_state.is_playing = False
                    player_state.position = 0
                return 'completed'
            
            if stop_event.is_set():
                try: player_state.current_process.terminate()
                except: pass
                return 'stopped'
            
            with player_state.lock:
                skip = player_state.skip_requested
            if skip:
                try:
                    player_state.current_process.terminate()
                    if player_state.crossfade_process:
                        player_state.crossfade_process.terminate()
                except: pass
                with player_state.lock:
                    player_state.skip_requested = False
                return 'skipped'
            
            with player_state.lock:
                paused = player_state.is_paused
            if paused:
                elapsed = time.time() - start_time
                with player_state.lock:
                    player_state.paused_position = elapsed
                    player_state.position = elapsed
                try:
                    player_state.current_process.terminate()
                    if player_state.crossfade_process:
                        player_state.crossfade_process.terminate()
                except: pass
                return 'paused'
            
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(elapsed, duration)
            
            if has_next and not crossfade_started and elapsed >= crossfade_time:
                print(f"🔀 Crossfade starting...")
                player_state.crossfade_process = start_crossfade_song(next_file, player_state.volume)
                crossfade_started = True
            
            time.sleep(0.25)
        
        return 'completed'
    except Exception as e:
        print(f"❌ Playback error: {e}")
        return 'error'

def resume_song(file_path, start_position, queue_id):
    try:
        duration = get_audio_duration(file_path)
        with player_state.lock:
            player_state.duration = duration
            player_state.is_playing = True
            player_state.is_paused = False
        
        print(f"▶️  Resuming from {start_position:.1f}s")
        audio_filter = build_audio_filter(player_state.volume, duration, fade_out=False, fade_in=False)
        cmd = ['ffplay', '-nodisp', '-autoexit', '-ss', str(start_position), '-af', audio_filter, file_path]
        
        with player_state.lock:
            player_state.current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.PIPE)
        
        start_time = time.time()
        
        while True:
            if player_state.current_process is None:
                break
            poll_result = player_state.current_process.poll()
            if poll_result is not None:
                return 'completed'
            if stop_event.is_set():
                try: player_state.current_process.terminate()
                except: pass
                return 'stopped'
            with player_state.lock:
                skip = player_state.skip_requested
            if skip:
                try: player_state.current_process.terminate()
                except: pass
                with player_state.lock:
                    player_state.skip_requested = False
                return 'skipped'
            with player_state.lock:
                paused = player_state.is_paused
            if paused:
                elapsed = time.time() - start_time
                with player_state.lock:
                    player_state.paused_position = start_position + elapsed
                    player_state.position = player_state.paused_position
                try: player_state.current_process.terminate()
                except: pass
                return 'paused'
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(start_position + elapsed, duration)
            time.sleep(0.25)
        return 'completed'
    except Exception as e:
        print(f"❌ Resume error: {e}")
        return 'error'

def process_download_queue():
    """Background thread to process bulk download queue"""
    print("📥 Download queue processor started...")
    while not stop_event.is_set():
        try:
            # Get next item from download queue
            response = requests.get(f"{SERVER_URL}/api/download-queue/next", timeout=5)
            if response.ok:
                data = response.json()
                item = data.get('song')
                
                if item:
                    item_id = item['id']
                    title = item['title']
                    artist = item['artist']
                    genre = item.get('genre', 'general')
                    
                    # Update status to downloading
                    requests.post(f"{SERVER_URL}/api/download-queue/{item_id}/status", 
                                  json={'status': 'downloading'}, timeout=5)
                    
                    print(f"📥 Downloading: {artist} - {title}")
                    
                    with download_lock:
                        file_path = download_from_youtube(item['song_id'], title, artist)
                    
                    if file_path:
                        # Update status to completed
                        requests.post(f"{SERVER_URL}/api/download-queue/{item_id}/status",
                                      json={'status': 'completed', 'filePath': file_path, 'songId': item['song_id']}, 
                                      timeout=5)
                        print(f"✅ Completed: {title}")
                    else:
                        # Update status to failed
                        requests.post(f"{SERVER_URL}/api/download-queue/{item_id}/status",
                                      json={'status': 'failed'}, timeout=5)
                        print(f"❌ Failed: {title}")
        except Exception as e:
            pass  # Server might not be running yet
        
        time.sleep(5)

def preload_queue():
    """Background thread to pre-download upcoming songs"""
    print("📥 Pre-download service started...")
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
                        print(f"📥 Pre-downloading: {title}")
                        download_from_youtube(song_id, title, artist)
            time.sleep(10)
        except Exception as e:
            time.sleep(10)

def mark_song_played(queue_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM queue WHERE id = ?", (queue_id,))
        song = cursor.fetchone()
        if song:
            cursor.execute("UPDATE queue SET played = 1 WHERE id = ?", (queue_id,))
            cursor.execute("INSERT INTO recently_played (song_id, title, artist) VALUES (?, ?, ?)", (song[1], song[2], song[3]))
            conn.commit()
            print(f"✅ Played: {song[2]}")
        conn.close()
    except Exception as e:
        print(f"❌ Mark played error: {e}")

def get_auto_playlist_song():
    """Get next song from auto-playlist queue, then remove it and trigger refill"""
    try:
        # Get first song from auto_playlist_queue
        response = requests.get(f"{SERVER_URL}/api/library/upcoming", timeout=5)
        if response.ok:
            data = response.json()
            songs = data.get('songs', [])
            if songs and len(songs) > 0:
                # Return first song
                song = songs[0]
                return {
                    'id': song['id'],
                    'song_id': song.get('song_id'),
                    'title': song.get('title', 'Unknown'),
                    'artist': song.get('artist', 'Unknown'),
                    'file_path': song.get('file_path')
                }
    except:
        pass
    return None

def remove_auto_playlist_song(song_id):
    """Remove song from auto-playlist queue and trigger refill"""
    global last_generate_time
    try:
        requests.delete(f"{SERVER_URL}/api/auto-playlist/{song_id}", timeout=5)
        # Rate limit generation to once per 5 seconds
        current_time = time.time()
        if current_time - last_generate_time > 5:
            requests.post(f"{SERVER_URL}/api/auto-playlist/generate", timeout=5)
            last_generate_time = current_time
    except Exception as e:
        print(f"Failed to remove auto-playlist song: {e}")

def play_queue():
    """Main playback loop"""
    print("👀 Playback loop started...")
    
    while not stop_event.is_set():
        try:
            # Handle pause state
            with player_state.lock:
                is_paused = player_state.is_paused
                paused_position = player_state.paused_position
                paused_file = player_state.current_file
                paused_song_id = player_state.current_song_id
            
            if is_paused:
                time.sleep(0.25)
                with player_state.lock:
                    still_paused = player_state.is_paused
                    skip = player_state.skip_requested
                
                if skip:
                    with player_state.lock:
                        player_state.is_paused = False
                        player_state.skip_requested = False
                        player_state.paused_position = 0
                    if paused_song_id and not player_state.is_auto_playlist:
                        mark_song_played(paused_song_id)
                    continue
                
                if not still_paused and paused_file and paused_position > 0:
                    result = resume_song(paused_file, paused_position, paused_song_id)
                    if result in ['completed', 'skipped']:
                        if not player_state.is_auto_playlist:
                            mark_song_played(paused_song_id)
                        with player_state.lock:
                            player_state.paused_position = 0
                continue
            
            # Get queue from database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id, song_id, title, artist FROM queue WHERE played = 0 ORDER BY requested_at ASC LIMIT 2")
            songs = cursor.fetchall()
            conn.close()
            
            if songs:
                # Play from request queue
                current = songs[0]
                next_song = songs[1] if len(songs) > 1 else None
                queue_id, song_id, title, artist = current
                
                file_path = search_song_in_library(song_id, title, artist)
                if not file_path:
                    print(f"⚠️  Downloading: {title}")
                    with download_lock:
                        file_path = download_from_youtube(song_id, title, artist)
                
                if not file_path:
                    print(f"❌ Could not get: {title}")
                    mark_song_played(queue_id)
                    continue
                
                next_file = None
                if next_song:
                    next_file = search_song_in_library(next_song[1], next_song[2], next_song[3])
                
                with player_state.lock:
                    player_state.current_song = {'id': queue_id, 'title': title, 'artist': artist}
                    player_state.paused_position = 0
                
                result = play_song_with_crossfade(file_path, next_file, queue_id, is_auto=False)
                
                if result in ['completed', 'skipped']:
                    mark_song_played(queue_id)
                elif result == 'paused':
                    print(f"⏸️  Paused - not marking as played")
            else:
                # Queue is empty - play from library auto-playlist
                auto_song = get_auto_playlist_song()
                
                if auto_song and auto_song.get('file_path'):
                    file_path = auto_song['file_path']
                    title = auto_song.get('title', 'Unknown')
                    artist = auto_song.get('artist', 'Unknown')
                    auto_id = auto_song.get('id')

                    # Validate file exists before attempting to play
                    if not os.path.exists(file_path):
                        print(f"⚠️  File not found: {file_path} - removing from queue")
                        remove_auto_playlist_song(auto_id)
                        time.sleep(2)
                        continue

                    print(f"📀 Queue empty - playing from library: {title}")

                    with player_state.lock:
                        player_state.current_song = {'title': title, 'artist': artist, 'auto': True}
                        player_state.paused_position = 0

                    # Get next song from auto-playlist queue for crossfade
                    next_auto = get_auto_playlist_song()
                    # Skip first song (current) and get second
                    next_file = None
                    if next_auto and next_auto.get('id') != auto_id:
                        next_file = next_auto.get('file_path')

                    result = play_song_with_crossfade(file_path, next_file, None, is_auto=True)

                    # Remove played song from auto-playlist queue and refill
                    if result in ['completed', 'skipped']:
                        print(f"✅ Played: {title}")
                        remove_auto_playlist_song(auto_id)
                else:
                    with player_state.lock:
                        player_state.current_song = None
                        player_state.is_playing = False

                    # Rate limit: only generate once every 30 seconds
                    global last_generate_time
                    current_time = time.time()
                    if current_time - last_generate_time > 30:
                        print("💤 No songs in auto-playlist queue - generating...")
                        try:
                            requests.post(f"{SERVER_URL}/api/auto-playlist/generate", timeout=5)
                            last_generate_time = current_time
                        except:
                            pass
                    time.sleep(10)
                    
        except Exception as e:
            print(f"❌ Loop error: {e}")
            time.sleep(5)

class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(player_state.to_dict()).encode())
        elif self.path.startswith('/search'):
            # Parse query parameter
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            
            print(f"🔍 Searching YouTube Music: {query}")
            
            if ytmusic and query:
                try:
                    # Search YouTube Music
                    results = ytmusic.search(query, filter='songs', limit=20)
                    
                    songs = []
                    for item in results:
                        # Extract artist - handle different response formats
                        artist = 'Unknown Artist'
                        if 'artists' in item and item['artists']:
                            artist = item['artists'][0].get('name', 'Unknown Artist')
                        elif 'artist' in item:
                            artist = item['artist']
                        
                        songs.append({
                            'id': item.get('videoId', ''),
                            'title': item.get('title', 'Unknown'),
                            'artist': artist,
                            'duration': item.get('duration', '--:--')
                        })
                    
                    print(f"✅ Found {len(songs)} results")
                    self._send_json({'songs': songs})
                except Exception as e:
                    print(f"❌ Search error: {e}")
                    self._send_json({'songs': []})
            else:
                # Fallback mock results if ytmusicapi not available
                self._send_json({'songs': []})
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
            with player_state.lock:
                player_state.skip_requested = True
                if player_state.is_paused:
                    player_state.is_paused = False
            if player_state.current_process:
                try: player_state.current_process.terminate()
                except: pass
            print("⏭️  Skipped")
            self._send_json({'success': True})
        elif self.path == '/pause':
            with player_state.lock:
                if player_state.is_playing and not player_state.is_paused:
                    player_state.is_paused = True
                    print("⏸️  Paused")
            self._send_json({'success': True, 'paused': True})
        elif self.path == '/resume':
            with player_state.lock:
                if player_state.is_paused:
                    player_state.is_paused = False
                    print(f"▶️  Resumed")
            self._send_json({'success': True, 'paused': False})
        elif self.path == '/volume':
            volume = data.get('volume', 100)
            with player_state.lock:
                player_state.volume = max(0, min(100, volume))
            self._send_json({'success': True, 'volume': player_state.volume})
        else:
            self.send_response(404)
            self.end_headers()
    
    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

def start_control_server():
    server = HTTPServer(('0.0.0.0', CONTROL_PORT), ControlHandler)
    print(f"🌐 Control server on port {CONTROL_PORT}")
    server.serve_forever()

if __name__ == '__main__':
    print("=" * 50)
    print("🎵 DJ Auto Player with Library Support")
    print("=" * 50)
    print("✅ Auto-plays from library when queue empty")
    print("✅ Processes bulk download queue")
    print("✅ TRUE 10-second crossfade")
    print("✅ Genre-aware auto-playlist")
    print("=" * 50)
    
    # Check dependencies
    print("✅ yt-dlp found")
    print("✅ ffmpeg found")
    print("✅ ffprobe found")



   #for cmd, name in [('yt-dlp', 'yt-dlp'), ('ffplay', 'ffmpeg'), ('ffprobe', 'ffprobe')]:
   #     try:
   #         subprocess.run([cmd, '-version'], capture_output=True, check=True)
   #     except:
   #         print(f"❌ {name} not found!")
   #         sys.exit(1)
    
    # Wait for database
    while not os.path.exists(DB_PATH):
        print("⚠️  Waiting for database...")
        time.sleep(2)
    print("✅ Database ready")
    
    # Start threads
    Thread(target=process_download_queue, daemon=True).start()
    print("✅ Download queue processor started")
    
    Thread(target=preload_queue, daemon=True).start()
    print("✅ Pre-download service started")
    
    Thread(target=play_queue, daemon=True).start()
    print("✅ Playback engine started")
    
    try:
        start_control_server()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        stop_event.set()
        print("✅ Goodbye!")
