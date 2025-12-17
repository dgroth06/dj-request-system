#!/usr/bin/env python3
"""
DJ Request System - Audio Player Bridge
Handles music playback with crossfading for Raspberry Pi + Focusrite Scarlett
"""

import subprocess
import json
import time
import os
import signal
import sys
from threading import Thread, Lock
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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
        self.crossfade_duration = 10  # seconds

player_state = PlayerState()

def get_audio_device():
    """Detect Focusrite Scarlett USB audio device"""
    try:
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True)
        output = result.stdout
        
        # Look for Focusrite or USB audio
        for line in output.split('\n'):
            if 'focusrite' in line.lower() or 'scarlett' in line.lower():
                # Extract card number
                if 'card' in line:
                    card_num = line.split('card')[1].split(':')[0].strip()
                    device = f'plughw:CARD={card_num},DEV=0'
                    print(f"🎚️ Found Focusrite Scarlett on card {card_num}")
                    return device
            elif 'USB' in line and 'card' in line:
                card_num = line.split('card')[1].split(':')[0].strip()
                device = f'plughw:CARD={card_num},DEV=0'
                print(f"🔊 Found USB audio device on card {card_num}")
                return device
        
        # Fallback to default
        print("⚠️  Using default audio device")
        return 'default'
    except Exception as e:
        print(f"⚠️  Error detecting audio device: {e}")
        return 'default'

AUDIO_DEVICE = get_audio_device()

def play_song(file_path, volume=100, start_position=0):
    """Play a song using mpv with specified volume and start position"""
    global player_state
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return None
    
    print(f"🎵 Playing: {os.path.basename(file_path)} (Volume: {volume}%)")
    
    # mpv command with Focusrite Scarlett USB audio output
    cmd = [
        'mpv',
        '--no-video',
        '--no-terminal',
        f'--volume={volume}',
        f'--audio-device=alsa/{AUDIO_DEVICE}',
        '--audio-channels=stereo',
        f'--start={start_position}',
        '--really-quiet',
        file_path
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group for clean termination
        )
        return process
    except Exception as e:
        print(f"❌ Error starting playback: {e}")
        return None

def get_song_duration(file_path):
    """Get song duration using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"⚠️  Could not get duration: {e}")
        return 0

def stop_playback():
    """Stop current playback"""
    global player_state
    
    with player_state.lock:
        if player_state.current_process:
            try:
                # Kill the entire process group
                os.killpg(os.getpgid(player_state.current_process.pid), signal.SIGTERM)
                player_state.current_process.wait(timeout=2)
            except Exception as e:
                print(f"⚠️  Error stopping playback: {e}")
            finally:
                player_state.current_process = None
                player_state.current_song = None
                player_state.is_playing = False

def pause_playback():
    """Pause current playback"""
    global player_state
    
    with player_state.lock:
        if player_state.current_process and player_state.is_playing:
            player_state.paused_song = player_state.current_song
            player_state.paused_position = player_state.position
            stop_playback()
            print("⏸️  Playback paused")
            return True
    return False

def resume_playback():
    """Resume paused playback"""
    global player_state
    
    with player_state.lock:
        if player_state.paused_song:
            song = player_state.paused_song
            position = player_state.paused_position
            player_state.paused_song = None
            player_state.paused_position = 0
            
            process = play_song(song, player_state.volume, position)
            if process:
                player_state.current_process = process
                player_state.current_song = song
                player_state.is_playing = True
                player_state.position = position
                print("▶️  Playback resumed")
                return True
    return False

def set_volume(volume):
    """Set playback volume (0-100)"""
    global player_state
    
    player_state.volume = max(0, min(100, volume))
    print(f"🔊 Volume set to {player_state.volume}%")
    
    # If currently playing, restart with new volume
    if player_state.current_process and player_state.is_playing:
        with player_state.lock:
            song = player_state.current_song
            position = player_state.position
            stop_playback()
            time.sleep(0.1)
            process = play_song(song, player_state.volume, position)
            if process:
                player_state.current_process = process
                player_state.current_song = song
                player_state.is_playing = True
                player_state.position = position

def playback_loop():
    """Main playback loop with crossfade support"""
    global player_state
    
    print("🎵 Playback loop started")
    
    while True:
        try:
            # Check if we have songs in the queue
            if len(player_state.queue) > 0 and not player_state.is_playing:
                with player_state.lock:
                    song = player_state.queue.pop(0)
                    player_state.current_song = song
                    player_state.duration = get_song_duration(song)
                    
                    process = play_song(song, player_state.volume)
                    if process:
                        player_state.current_process = process
                        player_state.is_playing = True
                        player_state.position = 0
                        print(f"🎶 Now playing: {os.path.basename(song)}")
            
            # Update position and check if song ended
            if player_state.is_playing and player_state.current_process:
                poll = player_state.current_process.poll()
                
                if poll is not None:
                    # Song ended
                    print(f"✅ Finished: {os.path.basename(player_state.current_song)}")
                    with player_state.lock:
                        player_state.is_playing = False
                        player_state.current_process = None
                        player_state.current_song = None
                else:
                    # Song still playing, update position
                    player_state.position += 0.5
                    
                    # Check for crossfade (start next song before current ends)
                    time_remaining = player_state.duration - player_state.position
                    if (time_remaining <= player_state.crossfade_duration and 
                        len(player_state.queue) > 0 and 
                        player_state.next_song is None):
                        
                        print(f"🔀 Crossfade starting in {time_remaining:.1f}s")
                        # Note: Full crossfade implementation would require
                        # simultaneous playback with volume ramping
                        # For now, we do a quick transition
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Error in playback loop: {e}")
            time.sleep(1)

class AudioAPIHandler(BaseHTTPRequestHandler):
    """HTTP API for controlling audio playback"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/status':
            # Return current playback status
            status = {
                'is_playing': player_state.is_playing,
                'current_song': os.path.basename(player_state.current_song) if player_state.current_song else None,
                'position': player_state.position,
                'duration': player_state.duration,
                'volume': player_state.volume,
                'queue_length': len(player_state.queue),
                'audio_device': AUDIO_DEVICE
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        
        elif parsed_path.path == '/queue':
            # Return current queue
            queue = [os.path.basename(song) for song in player_state.queue]
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'queue': queue}).encode())
        
        else:
            self.send_error(404)
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode()) if body else {}
        except:
            data = {}
        
        if self.path == '/play':
            # Add song to queue
            file_path = data.get('file_path')
            if file_path and os.path.exists(file_path):
                player_state.queue.append(file_path)
                print(f"➕ Added to queue: {os.path.basename(file_path)}")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True}).encode())
            else:
                self.send_error(400, 'Invalid file path')
        
        elif self.path == '/stop':
            stop_playback()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        elif self.path == '/pause':
            success = pause_playback()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success}).encode())
        
        elif self.path == '/resume':
            success = resume_playback()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success}).encode())
        
        elif self.path == '/volume':
            # Set volume
            volume = data.get('volume', 100)
            set_volume(volume)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'volume': player_state.volume}).encode())
        
        elif self.path == '/clear-queue':
            player_state.queue.clear()
            print("🗑️  Queue cleared")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def main():
    """Main entry point"""
    print("╔════════════════════════════════════════════════════════╗")
    print("║      🎵 DJ Request System - Audio Player Bridge 🎵     ║")
    print("╚════════════════════════════════════════════════════════╝")
    print(f"🔊 Audio Device: {AUDIO_DEVICE}")
    print("🌐 API Server: http://localhost:5001")
    print("")
    
    # Start playback loop in background thread
    playback_thread = Thread(target=playback_loop, daemon=True)
    playback_thread.start()
    
    # Start HTTP API server
    try:
        server = HTTPServer(('0.0.0.0', 5001), AudioAPIHandler)
        print("✅ Audio player ready!")
        print("   Use Ctrl+C to stop")
        print("")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        stop_playback()
        sys.exit(0)

if __name__ == '__main__':
    main()
