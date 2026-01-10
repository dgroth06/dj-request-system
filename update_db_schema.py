import sqlite3

DB_PATH = 'dj_requests.db'

print("🔧 Updating database schema...")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if requester_name column exists in queue table
cursor.execute("PRAGMA table_info(queue)")
columns = [column[1] for column in cursor.fetchall()]

if 'requester_name' not in columns:
    print("  → Adding requester_name column to queue table...")
    cursor.execute('ALTER TABLE queue ADD COLUMN requester_name TEXT DEFAULT "Anonymous"')
    print("  ✅ Added requester_name column")
else:
    print("  ✓ requester_name column already exists")

# Create auto_playlist_queue table
print("  → Creating auto_playlist_queue table...")
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
print("  ✅ Created auto_playlist_queue table")

conn.commit()
conn.close()

print("\n✅ Database schema updated successfully!")
