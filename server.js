const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const http = require('http');
const socketIo = require('socket.io');
const fetch = require('node-fetch');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const PORT = 3000;
const DB_PATH = path.join(__dirname, 'dj_requests.db');
const ADMIN_PASSWORD = '22706';

// Middleware
app.use(cors());
app.use(express.json());

// Password protection middleware for admin pages
function requireAuth(req, res, next) {
  const auth = req.headers.authorization;
  
  if (!auth) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Admin Area"');
    return res.status(401).send('Authentication required');
  }
  
  const credentials = Buffer.from(auth.split(' ')[1], 'base64').toString();
  const [username, password] = credentials.split(':');
  
  if (password === ADMIN_PASSWORD) {
    next();
  } else {
    res.setHeader('WWW-Authenticate', 'Basic realm="Admin Area"');
    return res.status(401).send('Invalid password');
  }
}

// Protect admin pages
app.get('/admin-player.html', requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'admin-player.html'));
});

app.get('/settings.html', requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'settings.html'));
});

// Serve other static files normally
app.use(express.static('public'));

// Database connection
const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) {
    console.error('Database connection error:', err);
  } else {
    console.log('✅ Connected to SQLite database');
  }
});

// Socket.IO connection
io.on('connection', (socket) => {
  console.log('🔌 Client connected');
  
  socket.on('disconnect', () => {
    console.log('🔌 Client disconnected');
  });
});

// Emit queue updates
function emitQueueUpdate() {
  db.all('SELECT * FROM queue WHERE played = 0 ORDER BY requested_at ASC', [], (err, rows) => {
    if (!err) {
      io.emit('queueUpdate', rows);
    }
  });
}

// Health check
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'DJ Request System is running!',
    timestamp: new Date().toISOString()
  });
});

// Get queue - FIX: Properly select artist field
app.get('/api/queue', (req, res) => {
  db.all(
    `SELECT 
      id, 
      song_id, 
      title, 
      artist,  
      requested_at, 
      played,
      requester_name
    FROM queue 
    WHERE played = 0 
    ORDER BY requested_at ASC`,
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

// Get current playing status - ENHANCED: Include automix info
app.get('/api/status', async (req, res) => {
  try {
    // Get player status from auto_player.py
    const playerResponse = await fetch('http://127.0.0.1:8888/status');
    const playerData = await playerResponse.json();
    
    // Get queue from database
    const queueData = await new Promise((resolve, reject) => {
      db.all(
        'SELECT id, song_id, title, artist, requested_at FROM queue WHERE played = 0 ORDER BY requested_at ASC LIMIT 10',
        [],
        (err, rows) => {
          if (err) reject(err);
          else resolve(rows);
        }
      );
    });
    
    res.json({
      currentSong: playerData.current_song,
      isPlaying: playerData.is_playing,
      isPaused: playerData.is_paused,
      isAutoPlaylist: playerData.is_auto_playlist,
      volume: playerData.volume,
      position: playerData.position,
      duration: playerData.duration,
      queue: queueData
    });
  } catch (error) {
    console.error('Status fetch error:', error);
    res.status(500).json({ error: 'Failed to fetch status' });
  }
});

// Search songs
app.get('/api/search', async (req, res) => {
  const { q } = req.query;
  
  if (!q || q.trim().length < 2) {
    return res.json({ songs: [] });
  }
  
  try {
    // Call Python music-api search
    const response = await fetch(`http://127.0.0.1:8888/search?q=${encodeURIComponent(q)}`);
    const data = await response.json();
    
    res.json({ songs: data.songs || [] });
  } catch (error) {
    console.error('Search error:', error);
    res.status(500).json({ error: 'Search failed' });
  }
});

// Request a song - FIX: Ensure artist is properly saved
app.post('/api/request', (req, res) => {
  const { song, requesterName } = req.body;
  
  if (!song || !song.id || !song.title) {
    return res.status(400).json({ error: 'Invalid song data' });
  }
  
  // Ensure artist has a value
  const artist = song.artist || 'Unknown Artist';
  
  console.log('🎵 Song request:', {
    title: song.title,
    artist: artist,
    requester: requesterName || 'Anonymous'
  });
  
  db.run(
    `INSERT INTO queue (song_id, title, artist, requester_name, requested_at, played) 
     VALUES (?, ?, ?, ?, datetime('now'), 0)`,
    [song.id, song.title, artist, requesterName || 'Anonymous'],
    function(err) {
      if (err) {
        console.error('Request insert error:', err);
        return res.status(500).json({ error: 'Failed to add song to queue' });
      }
      
      console.log(`✅ Song added to queue (ID: ${this.lastID})`);
      emitQueueUpdate();
      res.json({ 
        success: true, 
        queueId: this.lastID,
        message: 'Song added to queue!' 
      });
    }
  );
});

// Get user's request count
app.get('/api/user-requests', (req, res) => {
  const { name } = req.query;
  
  if (!name) {
    return res.json({ count: 0 });
  }
  
  db.get(
    'SELECT COUNT(*) as count FROM queue WHERE requester_name = ? AND played = 0',
    [name],
    (err, row) => {
      if (err) {
        console.error('User request count error:', err);
        return res.status(500).json({ error: 'Failed to fetch user requests' });
      }
      res.json({ count: row.count });
    }
  );
});

// Get recently played songs
app.get('/api/recently-played', (req, res) => {
  db.all(
    'SELECT song_id, title, artist FROM recently_played ORDER BY played_at DESC LIMIT 50',
    [],
    (err, rows) => {
      if (err) {
        console.error('Recently played fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch recently played' });
      }
      res.json({ songs: rows });
    }
  );
});

// Get settings
app.get('/api/settings', (req, res) => {
  db.get('SELECT * FROM settings WHERE id = 1', [], (err, row) => {
    if (err) {
      console.error('Settings fetch error:', err);
      return res.status(500).json({ error: 'Failed to fetch settings' });
    }
    
    if (!row) {
      // Return default settings if none exist
      return res.json({
        theme: 'general',
        welcome_title: 'DJ Song Requests',
        welcome_subtitle: 'Request your favorite songs!',
        colors: {
          primary: '#8b5cf6',
          secondary: '#ec4899',
          background: '#1a1625'
        },
        explicit_allowed: true
      });
    }
    
    // Parse JSON fields
    const settings = {
      ...row,
      colors: typeof row.colors === 'string' ? JSON.parse(row.colors) : row.colors
    };
    
    res.json(settings);
  });
});

// Update settings
app.post('/api/settings', (req, res) => {
  const { theme, welcomeTitle, welcomeSubtitle, colors, explicitAllowed } = req.body;
  
  const colorsJson = JSON.stringify(colors);
  
  db.run(
    `INSERT OR REPLACE INTO settings (id, theme, welcome_title, welcome_subtitle, colors, explicit_allowed)
     VALUES (1, ?, ?, ?, ?, ?)`,
    [theme, welcomeTitle, welcomeSubtitle, colorsJson, explicitAllowed ? 1 : 0],
    (err) => {
      if (err) {
        console.error('Settings update error:', err);
        return res.status(500).json({ error: 'Failed to update settings' });
      }
      
      console.log('✅ Settings updated');
      io.emit('settingsUpdate', { theme, welcomeTitle, welcomeSubtitle, colors, explicitAllowed });
      res.json({ success: true });
    }
  );
});

// Clear queue
app.delete('/api/queue/clear', (req, res) => {
  db.run('DELETE FROM queue WHERE played = 0', function(err) {
    if (err) {
      console.error('Queue clear error:', err);
      return res.status(500).json({ error: 'Failed to clear queue' });
    }
    
    console.log(`🗑️ Cleared ${this.changes} songs from queue`);
    emitQueueUpdate();
    res.json({ success: true, cleared: this.changes });
  });
});

// Get random song from library for auto-playlist
app.get('/api/library/random', (req, res) => {
  const { theme } = req.query;
  
  let query = 'SELECT * FROM music_library WHERE downloaded = 1';
  const params = [];
  
  if (theme && theme !== 'general') {
    query += ' AND genre = ?';
    params.push(theme);
  }
  
  query += ' ORDER BY RANDOM() LIMIT 1';
  
  db.get(query, params, (err, row) => {
    if (err) {
      console.error('Library random song error:', err);
      return res.status(500).json({ error: 'Failed to get random song' });
    }
    
    if (!row) {
      return res.json({ song: null });
    }
    
    res.json({ 
      song: {
        song_id: row.song_id,
        title: row.title,
        artist: row.artist,
        file_path: row.file_path
      }
    });
  });
});

// Get upcoming auto-playlist songs (for preview in admin)
app.get('/api/library/upcoming', (req, res) => {
  // Get songs from auto_playlist_queue table
  db.all(
    'SELECT * FROM auto_playlist_queue ORDER BY queue_position ASC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Auto-playlist queue error:', err);
        return res.status(500).json({ error: 'Failed to get auto-playlist queue' });
      }
      
      const songs = rows.map(row => ({
        id: row.id,
        song_id: row.song_id,
        title: row.title,
        artist: row.artist,
        file_path: row.file_path,
        queue_position: row.queue_position,
        source: 'auto_playlist'
      }));
      
      res.json({ songs: songs });
    }
  );
});

// Generate auto-playlist queue (fills up to 5 songs)
app.post('/api/auto-playlist/generate', (req, res) => {
  // First, check how many songs are already in queue
  db.get('SELECT COUNT(*) as count FROM auto_playlist_queue', [], (err, result) => {
    if (err) {
      console.error('Auto-playlist count error:', err);
      return res.status(500).json({ error: 'Failed to count queue' });
    }
    
    const currentCount = result.count;
    const needed = 5 - currentCount;
    
    if (needed <= 0) {
      return res.json({ success: true, added: 0, message: 'Queue already full' });
    }
    
    // Get random songs from library that aren't already in auto-playlist queue
    const { theme } = req.body;
    let query = `
      SELECT * FROM music_library 
      WHERE downloaded = 1 
      AND id NOT IN (SELECT song_id FROM auto_playlist_queue)
    `;
    const params = [];
    
    if (theme && theme !== 'general') {
      query += ' AND genre = ?';
      params.push(theme);
    }
    
    query += ` ORDER BY RANDOM() LIMIT ${needed}`;
    
    db.all(query, params, (err, rows) => {
      if (err) {
        console.error('Library fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch library songs' });
      }
      
      if (rows.length === 0) {
        return res.json({ success: true, added: 0, message: 'No songs available in library' });
      }
      
      let added = 0;
      const insertPromises = rows.map((row, index) => {
        return new Promise((resolve) => {
          db.run(
            `INSERT INTO auto_playlist_queue (song_id, title, artist, file_path, queue_position)
             VALUES (?, ?, ?, ?, ?)`,
            [row.id, row.title, row.artist, row.file_path, currentCount + index + 1],
            function(err) {
              if (!err) added++;
              resolve();
            }
          );
        });
      });
      
      Promise.all(insertPromises).then(() => {
        console.log(`🎲 Generated ${added} auto-playlist songs`);
        res.json({ success: true, added: added });
      });
    });
  });
});

// Remove song from auto-playlist queue
app.delete('/api/auto-playlist/:id', (req, res) => {
  const { id } = req.params;
  
  db.run('DELETE FROM auto_playlist_queue WHERE id = ?', [id], function(err) {
    if (err) {
      console.error('Auto-playlist delete error:', err);
      return res.status(500).json({ error: 'Failed to delete song' });
    }
    
    // Reorder remaining songs
    db.run(`
      UPDATE auto_playlist_queue 
      SET queue_position = (
        SELECT COUNT(*) 
        FROM auto_playlist_queue AS aq2 
        WHERE aq2.queue_position < auto_playlist_queue.queue_position
      ) + 1
    `, [], (err) => {
      if (err) {
        console.error('Reorder error:', err);
      }
      console.log(`🗑️ Removed song from auto-playlist queue`);
      res.json({ success: true });
    });
  });
});

// Clear entire auto-playlist queue
app.delete('/api/auto-playlist/clear', (req, res) => {
  db.run('DELETE FROM auto_playlist_queue', function(err) {
    if (err) {
      console.error('Auto-playlist clear error:', err);
      return res.status(500).json({ error: 'Failed to clear queue' });
    }
    
    console.log(`🗑️ Cleared auto-playlist queue`);
    res.json({ success: true, cleared: this.changes });
  });
});

// Add songs to bulk download queue
app.post('/api/download-queue/bulk', (req, res) => {
  const { songs, genre } = req.body;
  
  if (!songs || !Array.isArray(songs) || songs.length === 0) {
    return res.status(400).json({ error: 'Invalid songs array' });
  }
  
  let added = 0;
  let skipped = 0;
  
  const insertSong = (song) => {
    return new Promise((resolve) => {
      // Check if already in queue
      db.get(
        'SELECT id FROM download_queue WHERE title = ? AND artist = ? AND status = "pending"',
        [song.title, song.artist],
        (err, existing) => {
          if (existing) {
            skipped++;
            resolve();
            return;
          }
          
          // Generate song_id from title
          const songId = (song.title || '').replace(/[^a-zA-Z0-9]/g, '_').substring(0, 50);
          
          db.run(
            `INSERT INTO download_queue (song_id, title, artist, genre, status) 
             VALUES (?, ?, ?, ?, 'pending')`,
            [songId, song.title, song.artist || 'Unknown Artist', genre || 'general'],
            function(err) {
              if (err) {
                console.error(`Failed to queue ${song.title}:`, err);
                skipped++;
              } else {
                added++;
              }
              resolve();
            }
          );
        }
      );
    });
  };
  
  Promise.all(songs.map(insertSong)).then(() => {
    console.log(`📥 Queued ${added} songs for download (${skipped} skipped)`);
    res.json({ 
      success: true, 
      added: added,
      skipped: skipped,
      total: songs.length
    });
  });
});

// Get download queue status
app.get('/api/download-queue', (req, res) => {
  db.all(
    'SELECT * FROM download_queue ORDER BY added_at DESC LIMIT 100',
    [],
    (err, rows) => {
      if (err) {
        console.error('Download queue fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch download queue' });
      }
      res.json({ queue: rows });
    }
  );
});

// Start server
server.listen(PORT, '0.0.0.0', () => {
  console.log(`
╔════════════════════════════════════════╗
║   🎵 DJ Request System Backend 🎵     ║
╠════════════════════════════════════════╣
║  Server running on port ${PORT}         ║
║  http://localhost:${PORT}               ║
║                                        ║
║  Access from network:                  ║
║  http://YOUR_IP:${PORT}                 ║
╚════════════════════════════════════════╝
  `);
});
