#!/usr/bin/env python3
"""
Add existing Music files to music_library database
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = 'dj_requests.db'
MUSIC_LIBRARY = 'Music'

print("🔧 Populating music library database...")

# Connect to database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get all music files
music_files = []
for file in Path(MUSIC_LIBRARY).glob('*.mp3'):
    if file.name == 'Placeholder':
        continue
    music_files.append(file)

print(f"📁 Found {len(music_files)} music files")

added = 0
skipped = 0

for file in music_files:
    filename = file.stem  # Without .mp3
    
    # Try to parse "Artist - Title" format
    if ' - ' in filename:
        parts = filename.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
    else:
        artist = 'Unknown Artist'
        title = filename
    
    # Generate a song_id from filename
    song_id = filename.replace(' ', '_').replace('-', '_')[:50]
    
    # Check if already exists
    cursor.execute('SELECT id FROM music_library WHERE file_path = ?', [str(file)])
    if cursor.fetchone():
        print(f"⏭️  Skipped (already exists): {filename}")
        skipped += 1
        continue
    
    # Insert into database
    try:
        cursor.execute(
            '''INSERT INTO music_library (song_id, title, artist, file_path, genre, downloaded)
               VALUES (?, ?, ?, ?, ?, 1)''',
            [song_id, title, artist, str(file), 'general']
        )
        print(f"✅ Added: {artist} - {title}")
        added += 1
    except Exception as e:
        print(f"❌ Error adding {filename}: {e}")

conn.commit()
conn.close()

print(f"\n🎵 Complete!")
print(f"   Added: {added}")
print(f"   Skipped: {skipped}")
print(f"   Total in library: {added + skipped}")
print("\n💡 Auto-playlist should now work!")
