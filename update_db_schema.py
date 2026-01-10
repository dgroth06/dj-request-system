import sqlite3

DB_PATH = 'dj_requests.db'

print("🔧 Adding auto_playlist_queue table...")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create auto_playlist_queue table
cursor.execute('''
CREATE TABLE IF NOT EXISTS auto_playlist_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    file_path TEXT NOT NULL,
    queue_position INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

print("✅ Database updated with auto_playlist_queue table!")
