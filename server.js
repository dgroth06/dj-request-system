// DJ Request System - Backend Server
// File: server.js

const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const { Server } = require('socket.io');
const http = require('http');
const path = require('path');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const PORT = process.env.PORT || 3000;
const MUSIC_LIBRARY = './Music';

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' })); // Allow larger payloads for bulk upload
app.use(express.static('public')); // Serve frontend files

// Ensure Music folder exists
if (!fs.existsSync(MUSIC_LIBRARY)) {
  fs.mkdirSync(MUSIC_LIBRARY, { recursive: true });
}

// Initialize YouTube Music API
let ytmusic = null;
let ytmusicReady = false;

// Initialize YTMusic asynchronously
(async () => {
  try {
    const YTMusicModule = await import('ytmusic-api');
    const YTMusicClass = YTMusicModule.default || YTMusicModule.YTMusic;
    ytmusic = new YTMusicClass();
    await ytmusic.initialize();
    ytmusicReady = true;
    console.log('✅ YouTube Music API initialized');
  } catch (err) {
    console.error('❌ Failed to initialize YouTube Music API:', err);
    console.log('⚠️  Server will run in mock mode without YouTube Music search');
  }
})();

// Initialize SQLite Database
const db = new sqlite3.Database('./dj_requests.db', (err) => {
  if (err) {
    console.error('❌ Database error:', err);
  } else {
    console.log('✅ Connected to SQLite database');
  }
});

// Genre mapping for themes
const THEME_GENRES = {
  wedding: ['pop', 'r&b', 'soul', 'classical', 'jazz', 'love songs', 'ballad', 'romantic'],
  country: ['country', 'folk', 'americana', 'bluegrass', 'western'],
  christian: ['christian', 'gospel', 'worship', 'contemporary christian', 'religious'],
  kids_party: ['kids', 'pop', 'disney', 'family', 'children', 'soundtrack'],
  corporate: ['pop', 'jazz', 'electronic', 'instrumental', 'ambient', 'lounge'],
  nightclub: ['edm', 'hip hop', 'dance', 'electronic', 'house', 'techno', 'rap', 'club'],
  retro: ['80s', '90s', 'classic rock', 'disco', 'oldies', 'funk', 'new wave'],
  latin: ['reggaeton', 'salsa', 'bachata', 'latin pop', 'merengue', 'latin', 'spanish'],
  general: [] // Empty = all genres allowed
};

// Create tables
db.serialize(() => {
  // Queue table
  db.run(`
    CREATE TABLE IF NOT EXISTS queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id TEXT NOT NULL,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      duration TEXT NOT NULL,
      thumbnail TEXT,
      requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      played BOOLEAN DEFAULT 0
    )
  `);

  // Recently played table (songs played in last hour)
  db.run(`
    CREATE TABLE IF NOT EXISTS recently_played (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id TEXT NOT NULL,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      played_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // User cooldowns table
  db.run(`
    CREATE TABLE IF NOT EXISTS user_cooldowns (
      ip_address TEXT PRIMARY KEY,
      last_request DATETIME NOT NULL
    )
  `);

  // User request tracking (separate from cooldowns)
  db.run(`
    CREATE TABLE IF NOT EXISTS user_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ip_address TEXT NOT NULL,
      queue_id INTEGER NOT NULL,
      requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (queue_id) REFERENCES queue(id)
    )
  `);

  // Music Library - tracks all downloaded songs with genre
  db.run(`
    CREATE TABLE IF NOT EXISTS music_library (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      duration TEXT,
      genre TEXT DEFAULT 'general',
      file_path TEXT,
      downloaded BOOLEAN DEFAULT 0,
      added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Download queue for bulk imports
  db.run(`
    CREATE TABLE IF NOT EXISTS download_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id TEXT NOT NULL,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      genre TEXT DEFAULT 'general',
      status TEXT DEFAULT 'pending',
      added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Settings storage
  db.run(`
    CREATE TABLE IF NOT EXISTS settings (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      theme TEXT DEFAULT 'general',
      explicit_allowed BOOLEAN DEFAULT 1,
      allowed_genres TEXT DEFAULT '["All Genres"]',
      colors TEXT DEFAULT '{"primary":"#8b5cf6","secondary":"#3b82f6","background":"#1e1b4e"}',
      event_name TEXT DEFAULT '',
      custom_message TEXT DEFAULT '',
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Insert default settings if not exists
  db.run(`
    INSERT OR IGNORE INTO settings (id, theme, explicit_allowed) 
    VALUES (1, 'general', 1)
  `);

  console.log('✅ Database tables ready');
});

// Helper function to clean old recently played songs (older than 1 hour)
const cleanRecentlyPlayed = () => {
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  db.run('DELETE FROM recently_played WHERE played_at < ?', [oneHourAgo]);
};

// Run cleanup every 5 minutes
setInterval(cleanRecentlyPlayed, 5 * 60 * 1000);

// Scan Music folder and update library
const scanMusicLibrary = () => {
  console.log('📂 Scanning music library...');
  
  if (!fs.existsSync(MUSIC_LIBRARY)) {
    console.log('⚠️ Music folder does not exist');
    return;
  }

  const files = fs.readdirSync(MUSIC_LIBRARY);
  const audioFiles = files.filter(f => 
    f.endsWith('.mp3') || f.endsWith('.m4a') || f.endsWith('.flac') || f.endsWith('.wav')
  );

  console.log(`📂 Found ${audioFiles.length} audio files`);

  audioFiles.forEach(file => {
    const filePath = path.join(MUSIC_LIBRARY, file);
    
    // Parse filename: "Artist - Title.mp3"
    const nameWithoutExt = file.replace(/\.(mp3|m4a|flac|wav)$/i, '');
    let artist = 'Unknown Artist';
    let title = nameWithoutExt;
    
    if (nameWithoutExt.includes(' - ')) {
      const parts = nameWithoutExt.split(' - ');
      artist = parts[0].trim();
      title = parts.slice(1).join(' - ').trim();
    }

    // Generate a song_id from the filename
    const songId = Buffer.from(nameWithoutExt).toString('base64').substring(0, 20);

    // Insert or update in library
    db.run(`
      INSERT OR REPLACE INTO music_library (song_id, title, artist, file_path, downloaded, genre)
      VALUES (?, ?, ?, ?, 1, COALESCE((SELECT genre FROM music_library WHERE song_id = ?), 'general'))
    `, [songId, title, artist, filePath, songId]);
  });

  console.log('✅ Music library scan complete');
};

// Scan on startup and every 5 minutes
scanMusicLibrary();
setInterval(scanMusicLibrary, 5 * 60 * 1000);

// ==================== API ROUTES ====================

// Health check
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    ytmusicReady,
    timestamp: new Date().toISOString()
  });
});

// Get current settings (used by all pages)
app.get('/api/settings', (req, res) => {
  db.get('SELECT * FROM settings WHERE id = 1', [], (err, row) => {
    if (err) {
      console.error('Settings fetch error:', err);
      return res.status(500).json({ error: 'Failed to fetch settings' });
    }
    
    if (row) {
      // Parse JSON fields
      try {
        row.allowed_genres = JSON.parse(row.allowed_genres || '["All Genres"]');
      } catch (e) {
        row.allowed_genres = ['All Genres'];
      }
      try {
        row.colors = JSON.parse(row.colors || '{}');
      } catch (e) {
        row.colors = { primary: '#8b5cf6', secondary: '#3b82f6', background: '#1e1b4e' };
      }
    }
    
    res.json({ settings: row || {} });
  });
});

// Update settings
app.post('/api/settings', (req, res) => {
  try {
    const { settings } = req.body;

    if (!settings) {
      return res.status(400).json({ error: 'Settings data required' });
    }

    const {
      theme,
      explicitAllowed,
      allowedGenres,
      colors,
      eventName,
      customMessage
    } = settings;

    db.run(`
      UPDATE settings SET
        theme = ?,
        explicit_allowed = ?,
        allowed_genres = ?,
        colors = ?,
        event_name = ?,
        custom_message = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = 1
    `, [
      theme || 'general',
      explicitAllowed ? 1 : 0,
      JSON.stringify(allowedGenres || ['All Genres']),
      JSON.stringify(colors || {}),
      eventName || '',
      customMessage || ''
    ], (err) => {
      if (err) {
        console.error('Settings update error:', err);
        return res.status(500).json({ error: 'Failed to update settings' });
      }

      console.log('✅ Settings updated:', theme);
      
      // Notify all clients that settings changed
      io.emit('settings_updated');
      
      res.json({ success: true });
    });
  } catch (error) {
    console.error('Settings update error:', error);
    res.status(500).json({ error: 'Failed to update settings' });
  }
});

// Search YouTube Music (filtered by theme)
app.get('/api/search', async (req, res) => {
  try {
    const { q } = req.query;

    if (!q || q.length < 2) {
      return res.status(400).json({ error: 'Query must be at least 2 characters' });
    }

    // Get current settings for filtering
    const settings = await new Promise((resolve, reject) => {
      db.get('SELECT * FROM settings WHERE id = 1', [], (err, row) => {
        if (err) return reject(err);
        if (row) {
          try {
            row.allowed_genres = JSON.parse(row.allowed_genres || '["All Genres"]');
          } catch (e) {
            row.allowed_genres = ['All Genres'];
          }
        }
        resolve(row);
      });
    });

    // If YouTube Music API isn't ready, return mock results for testing
    if (!ytmusicReady || !ytmusic) {
      console.log('Using mock search results (YouTube Music API not available)');
      const mockSongs = [
        { id: `mock1_${Date.now()}`, title: `${q} - Original Mix`, artist: 'Artist Name', duration: '3:45', explicit: false },
        { id: `mock2_${Date.now()}`, title: `${q} (Extended Version)`, artist: 'DJ Artist', duration: '5:20', explicit: false },
        { id: `mock3_${Date.now()}`, title: `${q} Remix`, artist: 'Remix Artist', duration: '4:10', explicit: false }
      ];
      return res.json({ songs: mockSongs });
    }

    // Search YouTube Music
    const results = await ytmusic.searchSongs(q);
    
    // Format results
    let songs = results.slice(0, 20).map(song => ({
      id: song.videoId,
      title: song.name,
      artist: song.artist?.name || 'Unknown Artist',
      duration: song.duration || 'N/A',
      thumbnail: song.thumbnails?.[0]?.url || null,
      explicit: song.isExplicit || false,
      album: song.album?.name || ''
    }));

    // Filter explicit content if not allowed
    if (settings && !settings.explicit_allowed) {
      songs = songs.filter(song => !song.explicit);
    }

    // Limit to 10 results
    songs = songs.slice(0, 10);

    res.json({ songs });
  } catch (error) {
    console.error('Search error:', error);
    res.status(500).json({ error: 'Failed to search YouTube Music' });
  }
});

// Get current queue
app.get('/api/queue', (req, res) => {
  db.all(
    'SELECT * FROM queue WHERE played = 0 ORDER BY requested_at ASC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Queue fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch queue' });
      }
      res.json({ queue: rows });
    }
  );
});

// Get recently played songs (last hour)
app.get('/api/recently-played', (req, res) => {
  cleanRecentlyPlayed();
  
  db.all(
    'SELECT song_id, title, artist FROM recently_played ORDER BY played_at DESC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Recently played fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch recently played' });
      }
      res.json({ recentlyPlayed: rows });
    }
  );
});

// Get user's request count in current queue
app.get('/api/user-request-count', (req, res) => {
  const ipAddress = req.ip || req.connection.remoteAddress;
  
  db.get(`
    SELECT COUNT(*) as count 
    FROM user_requests ur
    JOIN queue q ON ur.queue_id = q.id
    WHERE ur.ip_address = ? AND q.played = 0
  `, [ipAddress], (err, row) => {
    if (err) {
      console.error('User count error:', err);
      return res.status(500).json({ error: 'Failed to get user count' });
    }
    res.json({ count: row?.count || 0 });
  });
});

// Add song request to queue
app.post('/api/request', async (req, res) => {
  try {
    const { song } = req.body;
    const ipAddress = req.ip || req.connection.remoteAddress;

    if (!song || !song.id || !song.title || !song.artist) {
      return res.status(400).json({ error: 'Invalid song data' });
    }

    // Check if song is already in queue
    const existingInQueue = await new Promise((resolve, reject) => {
      db.get(
        'SELECT id FROM queue WHERE song_id = ? AND played = 0',
        [song.id],
        (err, row) => {
          if (err) return reject(err);
          resolve(row);
        }
      );
    });

    if (existingInQueue) {
      return res.status(400).json({ error: 'This song is already in the queue' });
    }

    // Check if song was recently played
    const recentlyPlayed = await new Promise((resolve, reject) => {
      db.get(
        'SELECT id FROM recently_played WHERE song_id = ?',
        [song.id],
        (err, row) => {
          if (err) return reject(err);
          resolve(row);
        }
      );
    });

    if (recentlyPlayed) {
      return res.status(400).json({ error: 'This song was played recently' });
    }

    // Check user's request count
    const userCount = await new Promise((resolve, reject) => {
      db.get(`
        SELECT COUNT(*) as count 
        FROM user_requests ur
        JOIN queue q ON ur.queue_id = q.id
        WHERE ur.ip_address = ? AND q.played = 0
      `, [ipAddress], (err, row) => {
        if (err) return reject(err);
        resolve(row?.count || 0);
      });
    });

    if (userCount >= 5) {
      return res.status(400).json({ error: 'You already have 5 songs in the queue' });
    }

    // Add to queue
    const queueId = await new Promise((resolve, reject) => {
      db.run(
        'INSERT INTO queue (song_id, title, artist, duration, thumbnail) VALUES (?, ?, ?, ?, ?)',
        [song.id, song.title, song.artist, song.duration || 'N/A', song.thumbnail || null],
        function(err) {
          if (err) return reject(err);
          resolve(this.lastID);
        }
      );
    });

    // Track user request
    db.run(
      'INSERT INTO user_requests (ip_address, queue_id) VALUES (?, ?)',
      [ipAddress, queueId]
    );

    console.log(`✅ Song requested: ${song.title} by ${song.artist}`);
    io.emit('queue_updated');
    
    res.json({ 
      success: true, 
      message: 'Song added to queue',
      queueId 
    });
  } catch (error) {
    console.error('Request error:', error);
    res.status(500).json({ error: 'Failed to add song to queue' });
  }
});

// Delete song from queue (admin)
app.delete('/api/queue/:id', (req, res) => {
  const { id } = req.params;

  db.run('DELETE FROM queue WHERE id = ? AND played = 0', [id], function(err) {
    if (err) {
      console.error('Queue delete error:', err);
      return res.status(500).json({ error: 'Failed to delete song' });
    }

    if (this.changes === 0) {
      return res.status(404).json({ error: 'Song not found' });
    }

    io.emit('queue_updated');
    res.json({ success: true });
  });
});

// Clear entire queue (DJ/Admin endpoint)
app.delete('/api/queue', (req, res) => {
  db.run('DELETE FROM queue WHERE played = 0', (err) => {
    if (err) {
      console.error('Queue clear error:', err);
      return res.status(500).json({ error: 'Failed to clear queue' });
    }

    io.emit('queue_updated');
    res.json({ success: true, message: 'Queue cleared' });
  });
});

// ==================== MUSIC LIBRARY MANAGEMENT ====================

// Get music library (optionally filtered by genre)
app.get('/api/library', (req, res) => {
  const { genre } = req.query;
  
  let query = 'SELECT * FROM music_library WHERE downloaded = 1';
  const params = [];
  
  if (genre && genre !== 'all') {
    query += ' AND genre = ?';
    params.push(genre);
  }
  
  query += ' ORDER BY artist, title';
  
  db.all(query, params, (err, rows) => {
    if (err) {
      console.error('Library fetch error:', err);
      return res.status(500).json({ error: 'Failed to fetch library' });
    }
    res.json({ library: rows });
  });
});

// Get library by theme (returns songs matching theme's genres)
app.get('/api/library/theme/:theme', (req, res) => {
  const { theme } = req.params;
  const themeGenres = THEME_GENRES[theme] || [];
  
  if (themeGenres.length === 0) {
    // General theme = all songs
    db.all(
      'SELECT * FROM music_library WHERE downloaded = 1 ORDER BY RANDOM()',
      [],
      (err, rows) => {
        if (err) {
          console.error('Library fetch error:', err);
          return res.status(500).json({ error: 'Failed to fetch library' });
        }
        res.json({ library: rows, theme, genres: ['all'] });
      }
    );
  } else {
    // Filter by theme's genres
    const placeholders = themeGenres.map(() => 'LOWER(genre) LIKE ?').join(' OR ');
    const params = themeGenres.map(g => `%${g.toLowerCase()}%`);
    
    db.all(
      `SELECT * FROM music_library WHERE downloaded = 1 AND (${placeholders}) ORDER BY RANDOM()`,
      params,
      (err, rows) => {
        if (err) {
          console.error('Library fetch error:', err);
          return res.status(500).json({ error: 'Failed to fetch library' });
        }
        res.json({ library: rows, theme, genres: themeGenres });
      }
    );
  }
});

// Update song genre
app.post('/api/library/:id/genre', (req, res) => {
  const { id } = req.params;
  const { genre } = req.body;
  
  if (!genre) {
    return res.status(400).json({ error: 'Genre required' });
  }
  
  db.run(
    'UPDATE music_library SET genre = ? WHERE id = ?',
    [genre.toLowerCase(), id],
    function(err) {
      if (err) {
        console.error('Genre update error:', err);
        return res.status(500).json({ error: 'Failed to update genre' });
      }
      
      if (this.changes === 0) {
        return res.status(404).json({ error: 'Song not found' });
      }
      
      res.json({ success: true });
    }
  );
});

// Bulk update genres
app.post('/api/library/bulk-genre', (req, res) => {
  const { songIds, genre } = req.body;
  
  if (!songIds || !Array.isArray(songIds) || !genre) {
    return res.status(400).json({ error: 'songIds array and genre required' });
  }
  
  const placeholders = songIds.map(() => '?').join(',');
  
  db.run(
    `UPDATE music_library SET genre = ? WHERE id IN (${placeholders})`,
    [genre.toLowerCase(), ...songIds],
    function(err) {
      if (err) {
        console.error('Bulk genre update error:', err);
        return res.status(500).json({ error: 'Failed to update genres' });
      }
      
      res.json({ success: true, updated: this.changes });
    }
  );
});

// Get all unique genres in library
app.get('/api/library/genres', (req, res) => {
  db.all(
    'SELECT DISTINCT genre, COUNT(*) as count FROM music_library WHERE downloaded = 1 GROUP BY genre ORDER BY count DESC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Genres fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch genres' });
      }
      res.json({ genres: rows });
    }
  );
});

// ==================== BULK UPLOAD / DOWNLOAD QUEUE ====================

// Add songs to download queue (bulk upload)
app.post('/api/download-queue/bulk', async (req, res) => {
  try {
    const { songs, genre } = req.body;
    
    if (!songs || !Array.isArray(songs)) {
      return res.status(400).json({ error: 'songs array required' });
    }
    
    const defaultGenre = genre || 'general';
    let added = 0;
    let skipped = 0;
    
    for (const song of songs) {
      // Can be { title, artist } or { query } or just a string
      let title, artist, searchQuery;
      
      if (typeof song === 'string') {
        searchQuery = song;
        const parts = song.split(' - ');
        if (parts.length >= 2) {
          artist = parts[0].trim();
          title = parts.slice(1).join(' - ').trim();
        } else {
          title = song;
          artist = 'Unknown';
        }
      } else {
        title = song.title || song.name || '';
        artist = song.artist || 'Unknown';
        searchQuery = `${artist} - ${title}`;
      }
      
      if (!title) {
        skipped++;
        continue;
      }
      
      // Check if already in library or download queue
      const existing = await new Promise((resolve, reject) => {
        db.get(
          `SELECT id FROM music_library WHERE LOWER(title) = LOWER(?) AND LOWER(artist) = LOWER(?)
           UNION
           SELECT id FROM download_queue WHERE LOWER(title) = LOWER(?) AND LOWER(artist) = LOWER(?)`,
          [title, artist, title, artist],
          (err, row) => {
            if (err) return reject(err);
            resolve(row);
          }
        );
      });
      
      if (existing) {
        skipped++;
        continue;
      }
      
      // Add to download queue
      await new Promise((resolve, reject) => {
        db.run(
          'INSERT INTO download_queue (song_id, title, artist, genre, status) VALUES (?, ?, ?, ?, ?)',
          [searchQuery, title, artist, defaultGenre, 'pending'],
          (err) => {
            if (err) return reject(err);
            resolve();
          }
        );
      });
      
      added++;
    }
    
    console.log(`📥 Bulk upload: ${added} added, ${skipped} skipped`);
    res.json({ success: true, added, skipped, total: songs.length });
  } catch (error) {
    console.error('Bulk upload error:', error);
    res.status(500).json({ error: 'Failed to process bulk upload' });
  }
});

// Get download queue status
app.get('/api/download-queue', (req, res) => {
  db.all(
    'SELECT * FROM download_queue ORDER BY added_at DESC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Download queue fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch download queue' });
      }
      
      // Group by status
      const pending = rows.filter(r => r.status === 'pending');
      const downloading = rows.filter(r => r.status === 'downloading');
      const completed = rows.filter(r => r.status === 'completed');
      const failed = rows.filter(r => r.status === 'failed');
      
      res.json({ 
        queue: rows,
        stats: {
          pending: pending.length,
          downloading: downloading.length,
          completed: completed.length,
          failed: failed.length,
          total: rows.length
        }
      });
    }
  );
});

// Clear completed/failed from download queue
app.delete('/api/download-queue/completed', (req, res) => {
  db.run(
    "DELETE FROM download_queue WHERE status IN ('completed', 'failed')",
    function(err) {
      if (err) {
        console.error('Clear download queue error:', err);
        return res.status(500).json({ error: 'Failed to clear download queue' });
      }
      res.json({ success: true, deleted: this.changes });
    }
  );
});

// Get next song to download (for auto_player.py to call)
app.get('/api/download-queue/next', (req, res) => {
  db.get(
    "SELECT * FROM download_queue WHERE status = 'pending' ORDER BY added_at ASC LIMIT 1",
    [],
    (err, row) => {
      if (err) {
        console.error('Download queue next error:', err);
        return res.status(500).json({ error: 'Failed to get next download' });
      }
      res.json({ song: row || null });
    }
  );
});

// Update download status (for auto_player.py to call)
app.post('/api/download-queue/:id/status', (req, res) => {
  const { id } = req.params;
  const { status, filePath, songId } = req.body;
  
  db.run(
    'UPDATE download_queue SET status = ? WHERE id = ?',
    [status, id],
    function(err) {
      if (err) {
        console.error('Download status update error:', err);
        return res.status(500).json({ error: 'Failed to update status' });
      }
      
      // If completed, add to library
      if (status === 'completed' && filePath) {
        db.get('SELECT * FROM download_queue WHERE id = ?', [id], (err, row) => {
          if (row) {
            db.run(
              'INSERT OR REPLACE INTO music_library (song_id, title, artist, genre, file_path, downloaded) VALUES (?, ?, ?, ?, ?, 1)',
              [songId || row.song_id, row.title, row.artist, row.genre, filePath]
            );
          }
        });
      }
      
      res.json({ success: true });
    }
  );
});

// ==================== AUTO-PLAYLIST FROM LIBRARY ====================

// Get random song from library for auto-playlist (filtered by current theme)
app.get('/api/library/random', async (req, res) => {
  try {
    // Get current settings
    const settings = await new Promise((resolve, reject) => {
      db.get('SELECT theme FROM settings WHERE id = 1', [], (err, row) => {
        if (err) return reject(err);
        resolve(row);
      });
    });
    
    const theme = settings?.theme || 'general';
    const themeGenres = THEME_GENRES[theme] || [];
    
    // Get recently played song IDs to exclude
    const recentIds = await new Promise((resolve, reject) => {
      db.all('SELECT song_id FROM recently_played', [], (err, rows) => {
        if (err) return reject(err);
        resolve(rows.map(r => r.song_id));
      });
    });
    
    // Get songs currently in queue to exclude
    const queueIds = await new Promise((resolve, reject) => {
      db.all('SELECT song_id FROM queue WHERE played = 0', [], (err, rows) => {
        if (err) return reject(err);
        resolve(rows.map(r => r.song_id));
      });
    });
    
    const excludeIds = [...recentIds, ...queueIds];
    
    // Build query
    let query = 'SELECT * FROM music_library WHERE downloaded = 1';
    const params = [];
    
    // Exclude recently played and queued
    if (excludeIds.length > 0) {
      const placeholders = excludeIds.map(() => '?').join(',');
      query += ` AND song_id NOT IN (${placeholders})`;
      params.push(...excludeIds);
    }
    
    // Filter by theme genres (unless general)
    if (themeGenres.length > 0) {
      const genreConditions = themeGenres.map(() => 'LOWER(genre) LIKE ?').join(' OR ');
      query += ` AND (${genreConditions})`;
      params.push(...themeGenres.map(g => `%${g.toLowerCase()}%`));
    }
    
    query += ' ORDER BY RANDOM() LIMIT 1';
    
    db.get(query, params, (err, row) => {
      if (err) {
        console.error('Random song error:', err);
        return res.status(500).json({ error: 'Failed to get random song' });
      }
      res.json({ song: row || null, theme });
    });
  } catch (error) {
    console.error('Random song error:', error);
    res.status(500).json({ error: 'Failed to get random song' });
  }
});

// ==================== STATS ====================

app.get('/api/stats', (req, res) => {
  const stats = {};
  
  db.get('SELECT COUNT(*) as count FROM queue WHERE played = 0', [], (err, row) => {
    stats.queueLength = row?.count || 0;
    
    db.get('SELECT COUNT(*) as count FROM recently_played', [], (err, row) => {
      stats.songsPlayed = row?.count || 0;
      
      db.get('SELECT COUNT(DISTINCT ip_address) as count FROM user_requests WHERE requested_at > datetime("now", "-1 hour")', [], (err, row) => {
        stats.activeUsers = row?.count || 0;
        
        db.get('SELECT COUNT(*) as count FROM music_library WHERE downloaded = 1', [], (err, row) => {
          stats.librarySize = row?.count || 0;
          
          res.json(stats);
        });
      });
    });
  });
});

// ==================== WEBSOCKET ====================

io.on('connection', (socket) => {
  console.log('👤 Client connected:', socket.id);

  socket.on('disconnect', () => {
    console.log('👤 Client disconnected:', socket.id);
  });
});

// ==================== START SERVER ====================

server.listen(PORT, '0.0.0.0', () => {
  console.log(`
╔════════════════════════════════════════╗
║   🎵 DJ Request System Backend 🎵     ║
╠════════════════════════════════════════╣
║  Server running on port ${PORT}         ║
║  http://localhost:${PORT}               ║
╚════════════════════════════════════════╝
  `);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n🛑 Shutting down gracefully...');
  db.close((err) => {
    if (err) {
      console.error('Error closing database:', err);
    } else {
      console.log('✅ Database closed');
    }
    process.exit(0);
  });
});