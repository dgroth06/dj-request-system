#!/usr/bin/env python3
"""
Fully Automated DJ Player - No GUI Required
Pre-downloads queue to prevent dead time
Perfect for Raspberry Pi deployment

FEATURES:
- TRUE crossfade with 10-second overlap (both songs play simultaneously)
- Pause/Resume without marking song as played
- Volume changes without interrupting playback
- Silence removal from start/end of songs
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
CROSSFADE_DURATION = 10  # seconds of overlap between songs
PRELOAD_COUNT = 3  # Number of songs to download ahead
SILENCE_THRESHOLD = '-50dB'  # Threshold for silence detection
SILENCE_DURATION = 0.5  # Minimum silence duration to trim (seconds)

# Audio player state
class PlayerState:
    def __init__(self):
        self.current_song = None
        self.current_song_id = None  # Queue ID of current song
        self.current_file = None  # File path of current song
        self.current_process = None
        self.crossfade_process = None  # Second process for crossfade
        self.next_song = None
        self.queue = []
        self.is_playing = False
        self.is_paused = False
        self.position = 0
        self.duration = 0
        self.volume = 100
        self.paused_position = 0
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
                'queue_length': len(self.queue),
                'volume': self.volume
            }

player_state = PlayerState()
stop_event = Event()
download_lock = Lock()

print(f"🎵 Automated DJ Player Starting...")
print(f"📁 Database: {DB_PATH}")
print(f"🎵 Music folder: {MUSIC_LIBRARY}")
print(f"🔀 Crossfade: {CROSSFADE_DURATION} seconds (TRUE overlap)")
print(f"📥 Pre-download: {PRELOAD_COUNT} songs ahead")
print(f"🔇 Silence removal: enabled")
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

def build_audio_filter(volume, duration=None, fade_out=False, fade_in=False):
    """Build ffmpeg audio filter string with silence removal and fades"""
    filters = []
    
    # Silence removal from start and end
    filters.append(f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION}:start_threshold={SILENCE_THRESHOLD}")
    filters.append(f"silenceremove=stop_periods=1:stop_duration={SILENCE_DURATION}:stop_threshold={SILENCE_THRESHOLD}")
    
    # Volume control
    filters.append(f"volume={volume / 100}")
    
    # Fade out at end of song (for crossfade)
    if fade_out and duration:
        fade_start = max(0, duration - CROSSFADE_DURATION)
        filters.append(f"afade=t=out:st={fade_start}:d={CROSSFADE_DURATION}")
    
    # Fade in at start of song (for crossfade)
    if fade_in:
        filters.append(f"afade=t=in:st=0:d={CROSSFADE_DURATION}")
    
    return ','.join(filters)

def start_crossfade_song(file_path, volume):
    """Start playing the next song with fade-in for crossfade overlap"""
    try:
        duration = get_audio_duration(file_path)
        
        # Build audio filter with fade in
        audio_filter = build_audio_filter(
            volume, 
            duration, 
            fade_out=False,  # Will be set when this becomes the main song
            fade_in=True  # Fade in for crossfade
        )
        
        cmd = [
            'ffplay',
            '-nodisp',
            '-autoexit',
            '-af', audio_filter,
            file_path
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE
        )
        
        print(f"🎵 Crossfade started: {os.path.basename(file_path)}")
        return process
        
    except Exception as e:
        print(f"❌ Crossfade start error: {e}")
        return None

def play_song_with_crossfade(file_path, next_file, queue_id):
    """
    Play a song with TRUE crossfade - starts next song 10 seconds before current ends.
    Returns: 'completed', 'skipped', 'paused', or 'error'
    """
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
        
        print(f"▶️  Playing: {os.path.basename(file_path)}")
        print(f"   Duration: {duration:.1f}s, Crossfade at: {crossfade_time:.1f}s")
        
        # Build audio filter - fade out if we have next song
        has_next = next_file is not None and os.path.exists(next_file)
        audio_filter = build_audio_filter(
            player_state.volume, 
            duration, 
            fade_out=has_next,
            fade_in=False
        )
        
        cmd = [
            'ffplay',
            '-nodisp',
            '-autoexit',
            '-af', audio_filter,
            file_path
        ]
        
        # Start playback
        with player_state.lock:
            player_state.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.PIPE
            )
        
        # Track position while playing
        start_time = time.time()
        
        while True:
            # Check if process ended
            if player_state.current_process is None:
                break
                
            poll_result = player_state.current_process.poll()
            
            if poll_result is not None:
                # Process ended naturally (song finished)
                with player_state.lock:
                    player_state.is_playing = False
                    player_state.position = 0
                return 'completed'
            
            # Check for stop event (shutdown)
            if stop_event.is_set():
                try:
                    player_state.current_process.terminate()
                except:
                    pass
                return 'stopped'
            
            # Check if skip was requested
            with player_state.lock:
                skip = player_state.skip_requested
            if skip:
                try:
                    player_state.current_process.terminate()
                    # Also kill crossfade if running
                    if player_state.crossfade_process:
                        player_state.crossfade_process.terminate()
                        player_state.crossfade_process = None
                except:
                    pass
                with player_state.lock:
                    player_state.skip_requested = False
                return 'skipped'
            
            # Check if pause was requested
            with player_state.lock:
                paused = player_state.is_paused
            if paused:
                # Save current position
                elapsed = time.time() - start_time
                with player_state.lock:
                    player_state.paused_position = elapsed
                    player_state.position = elapsed
                try:
                    player_state.current_process.terminate()
                    # Also kill crossfade if running
                    if player_state.crossfade_process:
                        player_state.crossfade_process.terminate()
                        player_state.crossfade_process = None
                except:
                    pass
                return 'paused'
            
            # Update position
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(elapsed, duration)
            
            # Start crossfade if it's time and we have a next song
            if has_next and not crossfade_started and elapsed >= crossfade_time:
                print(f"🔀 Starting crossfade with {CROSSFADE_DURATION}s remaining...")
                player_state.crossfade_process = start_crossfade_song(next_file, player_state.volume)
                crossfade_started = True
            
            time.sleep(0.25)
        
        return 'completed'
        
    except Exception as e:
        print(f"❌ Playback error: {e}")
        with player_state.lock:
            player_state.is_playing = False
        return 'error'

def resume_song(file_path, start_position, queue_id):
    """Resume a paused song from a specific position"""
    try:
        duration = get_audio_duration(file_path)
        
        with player_state.lock:
            player_state.duration = duration
            player_state.is_playing = True
            player_state.is_paused = False
            player_state.skip_requested = False
            player_state.current_file = file_path
            player_state.current_song_id = queue_id
        
        print(f"▶️  Resuming: {os.path.basename(file_path)} from {start_position:.1f}s")
        
        # Build audio filter (no fade in since we're resuming)
        audio_filter = build_audio_filter(
            player_state.volume, 
            duration, 
            fade_out=False,
            fade_in=False
        )
        
        cmd = [
            'ffplay',
            '-nodisp',
            '-autoexit',
            '-ss', str(start_position),
            '-af', audio_filter,
            file_path
        ]
        
        # Start playback
        with player_state.lock:
            player_state.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.PIPE
            )
        
        # Track position while playing
        start_time = time.time()
        
        while True:
            if player_state.current_process is None:
                break
                
            poll_result = player_state.current_process.poll()
            
            if poll_result is not None:
                with player_state.lock:
                    player_state.is_playing = False
                    player_state.position = 0
                return 'completed'
            
            if stop_event.is_set():
                try:
                    player_state.current_process.terminate()
                except:
                    pass
                return 'stopped'
            
            with player_state.lock:
                skip = player_state.skip_requested
            if skip:
                try:
                    player_state.current_process.terminate()
                except:
                    pass
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
                try:
                    player_state.current_process.terminate()
                except:
                    pass
                return 'paused'
            
            elapsed = time.time() - start_time
            with player_state.lock:
                player_state.position = min(start_position + elapsed, duration)
            
            time.sleep(0.25)
        
        return 'completed'
        
    except Exception as e:
        print(f"❌ Resume error: {e}")
        with player_state.lock:
            player_state.is_playing = False
        return 'error'

def preload_queue():
    """Background thread to pre-download upcoming songs"""
    print("📥 Starting pre-download service...")
    
    while not stop_event.is_set():
        try:
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
            
            for queue_id, song_id, title, artist in songs:
                if stop_event.is_set():
                    break
                
                file_path = search_song_in_library(song_id, title, artist)
                
                if not file_path:
                    with download_lock:
                        print(f"📥 Pre-downloading: {title} by {artist}")
                        file_path = download_from_youtube(song_id, title, artist)
                        if file_path:
                            print(f"✅ Ready: {title}")
            
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

def play_queue():
    """Main playback loop - plays queue with TRUE crossfading"""
    print("👀 Starting playback loop...")
    
    while not stop_event.is_set():
        try:
            # Check if we're paused
            with player_state.lock:
                is_paused = player_state.is_paused
                paused_position = player_state.paused_position
                paused_file = player_state.current_file
                paused_song_id = player_state.current_song_id
            
            if is_paused:
                # Wait for unpause
                time.sleep(0.25)
                
                # Check if we've been unpaused
                with player_state.lock:
                    still_paused = player_state.is_paused
                    skip = player_state.skip_requested
                
                if skip:
                    # Skip was requested while paused
                    with player_state.lock:
                        player_state.is_paused = False
                        player_state.skip_requested = False
                        player_state.paused_position = 0
                    if paused_song_id:
                        mark_song_played(paused_song_id)
                    continue
                
                if not still_paused and paused_file and paused_position > 0:
                    # Resume playback
                    result = resume_song(paused_file, paused_position, paused_song_id)
                    
                    if result == 'completed':
                        mark_song_played(paused_song_id)
                        with player_state.lock:
                            player_state.paused_position = 0
                    elif result == 'skipped':
                        mark_song_played(paused_song_id)
                        with player_state.lock:
                            player_state.paused_position = 0
                    elif result == 'paused':
                        # Paused again, don't mark as played
                        pass
                    elif result == 'stopped':
                        return
                
                continue
            
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
                with player_state.lock:
                    player_state.current_song = None
                    player_state.is_playing = False
                time.sleep(5)
                continue
            
            current = songs[0]
            next_song = songs[1] if len(songs) > 1 else None
            
            queue_id, song_id, title, artist = current
            
            file_path = search_song_in_library(song_id, title, artist)
            
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
            
            # Update current song info
            with player_state.lock:
                player_state.current_song = {'id': queue_id, 'title': title, 'artist': artist}
                player_state.next_song = next_file
                player_state.paused_position = 0
            
            # Play the song with crossfade
            result = play_song_with_crossfade(file_path, next_file, queue_id)
            
            # Handle result - ONLY mark as played for completed or skipped
            if result == 'completed':
                mark_song_played(queue_id)
            elif result == 'skipped':
                mark_song_played(queue_id)
            elif result == 'paused':
                # DO NOT mark as played - song will resume
                print(f"⏸️  Song paused at {player_state.paused_position:.1f}s - NOT marking as played")
            elif result == 'stopped':
                return
            elif result == 'error':
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
            with player_state.lock:
                player_state.skip_requested = True
                # If paused, also unpause so the skip can be processed
                if player_state.is_paused:
                    player_state.is_paused = False
            
            if player_state.current_process:
                try:
                    player_state.current_process.terminate()
                except:
                    pass
            if player_state.crossfade_process:
                try:
                    player_state.crossfade_process.terminate()
                except:
                    pass
            
            print("⏭️  Skipped by admin")
            self._send_json({'success': True})
            
        elif self.path == '/pause':
            with player_state.lock:
                if player_state.is_playing and not player_state.is_paused:
                    player_state.is_paused = True
                    print("⏸️  Paused by admin")
            
            self._send_json({'success': True, 'paused': True})
            
        elif self.path == '/resume':
            with player_state.lock:
                if player_state.is_paused:
                    player_state.is_paused = False
                    print(f"▶️  Resumed by admin (from {player_state.paused_position:.1f}s)")
            
            self._send_json({'success': True, 'paused': False})
            
        elif self.path == '/volume':
            # Just update volume state - doesn't interrupt playback
            # Volume takes effect on next song
            volume = data.get('volume', 100)
            set_volume(volume)
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
    print("=" * 60)
    print("🎵 Fully Automated DJ Player")
    print("=" * 60)
    print()
    print("✅ No GUI required - runs completely headless")
    print("✅ Auto-downloads songs from queue")
    print("✅ TRUE crossfade - 10 second overlap")
    print("✅ Silence removal from start/end of songs")
    print("✅ Pause/Resume WITHOUT marking as played")
    print("✅ Volume changes don't interrupt playback")
    print("✅ Perfect for Raspberry Pi")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
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
    
    try:
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
        print("✅ ffprobe found")
    except:
        print("❌ ERROR: ffprobe not found! Install: sudo apt install ffmpeg")
        sys.exit(1)
    
    if not os.path.exists(DB_PATH):
        print(f"⚠️  Waiting for database...")
        while not os.path.exists(DB_PATH):
            time.sleep(2)
    print("✅ Database ready")
    print()
    
    preload_thread = Thread(target=preload_queue, daemon=True)
    preload_thread.start()
    print("✅ Pre-download service started")
    
    playback_thread = Thread(target=play_queue, daemon=True)
    playback_thread.start()
    print("✅ Playback engine started")
    print()
    
    try:
        start_control_server()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        stop_event.set()
        if player_state.current_process:
            player_state.current_process.terminate()
        if player_state.crossfade_process:
            player_state.crossfade_process.terminate()
        print("✅ Goodbye!")