import sqlite3

DB_PATH = 'dj_requests.db'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create queue table
cursor.execute('''
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    requester_name TEXT DEFAULT 'Anonymous',
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    played INTEGER DEFAULT 0
)
''')

# Create recently_played table
cursor.execute('''
CREATE TABLE IF NOT EXISTS recently_played (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    played_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

# Create settings table
cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    theme TEXT DEFAULT 'general',
    welcome_title TEXT DEFAULT 'DJ Song Requests',
    welcome_subtitle TEXT DEFAULT 'Request your favorite songs!',
    colors TEXT DEFAULT '{"primary":"#8b5cf6","secondary":"#ec4899","background":"#1a1625"}',
    explicit_allowed INTEGER DEFAULT 1
)
''')

# Create music_library table
cursor.execute('''
CREATE TABLE IF NOT EXISTS music_library (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT UNIQUE,
    title TEXT,
    artist TEXT,
    file_path TEXT,
    genre TEXT DEFAULT 'general',
    downloaded INTEGER DEFAULT 1
)
''')

# Create download_queue table
cursor.execute('''
CREATE TABLE IF NOT EXISTS download_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT,
    title TEXT,
    artist TEXT,
    genre TEXT DEFAULT 'general',
    status TEXT DEFAULT 'pending',
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

print("✅ Database initialized successfully!")
