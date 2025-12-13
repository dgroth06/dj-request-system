// DJ Request System - Backend Server
// File: server.js

const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const { Server } = require('socket.io');
const http = require('http');
const path = require('path');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public')); // Serve frontend files

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

  // Default playlist table
  db.run(`
    CREATE TABLE IF NOT EXISTS default_playlist (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id TEXT NOT NULL,
      title TEXT NOT NULL,
      artist TEXT NOT NULL,
      duration TEXT NOT NULL,
      thumbnail TEXT,
      added_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

// ==================== API ROUTES ====================

// Health check
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    ytmusicReady,
    timestamp: new Date().toISOString()
  });
});

// Search YouTube Music
app.get('/api/search', async (req, res) => {
  try {
    const { q } = req.query;

    if (!q || q.length < 2) {
      return res.status(400).json({ error: 'Query must be at least 2 characters' });
    }

    // If YouTube Music API isn't ready, return mock results for testing
    if (!ytmusicReady || !ytmusic) {
      console.log('Using mock search results (YouTube Music API not available)');
      const mockSongs = [
        { id: `mock1_${Date.now()}`, title: `${q} - Original Mix`, artist: 'Artist Name', duration: '3:45', explicit: false },
        { id: `mock2_${Date.now()}`, title: `${q} (Extended Version)`, artist: 'DJ Artist', duration: '5:20', explicit: false },
        { id: `mock3_${Date.now()}`, title: `${q} Remix`, artist: 'Remix Artist', duration: '4:10', explicit: false },
        { id: `mock4_${Date.now()}`, title: `Best of ${q}`, artist: 'Various Artists', duration: '6:30', explicit: false },
        { id: `mock5_${Date.now()}`, title: `${q} Live Performance`, artist: 'Live Band', duration: '4:55', explicit: false }
      ];
      return res.json({ songs: mockSongs.slice(0, 10) });
    }

    // Get current settings for filtering
    const settings = await new Promise((resolve, reject) => {
      db.get('SELECT * FROM settings WHERE id = 1', [], (err, row) => {
        if (err) return reject(err);
        if (row) {
          row.allowed_genres = JSON.parse(row.allowed_genres || '["All Genres"]');
          row.colors = JSON.parse(row.colors || '{}');
        }
        resolve(row);
      });
    });

    // Search YouTube Music
    const results = await ytmusic.searchSongs(q);
    
    // Format and filter results
    let songs = results.slice(0, 20).map(song => ({
      id: song.videoId,
      title: song.name,
      artist: song.artist?.name || 'Unknown Artist',
      duration: song.duration || 'N/A',
      thumbnail: song.thumbnails?.[0]?.url || null,
      explicit: song.isExplicit || false
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

// Clear user cooldown (for testing/debugging)
app.delete('/api/cooldown', (req, res) => {
  const ipAddress = req.ip || req.connection.remoteAddress;
  
  db.run('DELETE FROM user_cooldowns WHERE ip_address = ?', [ipAddress], (err) => {
    if (err) {
      console.error('Cooldown clear error:', err);
      return res.status(500).json({ error: 'Failed to clear cooldown' });
    }
    console.log(`✅ Cleared cooldown for ${ipAddress}`);
    res.json({ success: true, message: 'Cooldown cleared' });
  });
});

// Clear ALL cooldowns (admin endpoint)
app.delete('/api/cooldowns/all', (req, res) => {
  db.run('DELETE FROM user_cooldowns', (err) => {
    if (err) {
      console.error('Cooldown clear all error:', err);
      return res.status(500).json({ error: 'Failed to clear cooldowns' });
    }
    console.log('✅ Cleared all cooldowns');
    res.json({ success: true, message: 'All cooldowns cleared' });
  });
});

// Get stats for admin dashboard
app.get('/api/stats', (req, res) => {
  const stats = {
    totalRequests: 0,
    activeUsers: 0,
    songsPlayed: 0,
    queueLength: 0
  };

  // Get total songs in queue
  db.get('SELECT COUNT(*) as count FROM queue WHERE played = 0', [], (err, row) => {
    if (!err && row) stats.queueLength = row.count;

    // Get total songs played today
    const today = new Date().toISOString().split('T')[0];
    db.get(
      'SELECT COUNT(*) as count FROM queue WHERE played = 1 AND DATE(requested_at) = ?',
      [today],
      (err, row) => {
        if (!err && row) stats.songsPlayed = row.count;

        // Get active users (requested in last hour)
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
        db.get(
          'SELECT COUNT(DISTINCT ip_address) as count FROM user_cooldowns WHERE last_request > ?',
          [oneHourAgo],
          (err, row) => {
            if (!err && row) stats.activeUsers = row.count;

            // Get total requests today
            db.get(
              'SELECT COUNT(*) as count FROM queue WHERE DATE(requested_at) = ?',
              [today],
              (err, row) => {
                if (!err && row) stats.totalRequests = row.count;
                res.json(stats);
              }
            );
          }
        );
      }
    );
  });
});

// Check user cooldown
const checkCooldown = (ipAddress) => {
  return new Promise((resolve, reject) => {
    db.get(
      'SELECT last_request FROM user_cooldowns WHERE ip_address = ?',
      [ipAddress],
      (err, row) => {
        if (err) return reject(err);
        
        if (!row) {
          console.log(`✅ No cooldown for ${ipAddress} - first request`);
          return resolve(true); // No cooldown record
        }
        
        const lastRequest = new Date(row.last_request);
        const now = new Date();
        const diffMs = now - lastRequest;
        const diffSeconds = diffMs / 1000;
        
        console.log(`⏱️ Cooldown check for ${ipAddress}:`);
        console.log(`   Last request: ${lastRequest.toISOString()}`);
        console.log(`   Current time: ${now.toISOString()}`);
        console.log(`   Time elapsed: ${diffSeconds.toFixed(1)} seconds`);
        console.log(`   Can request: ${diffSeconds >= 30 ? 'YES' : 'NO'}`);
        
        resolve(diffSeconds >= 30); // 30 second cooldown
      }
    );
  });
};

// Update user cooldown
const updateCooldown = (ipAddress) => {
  return new Promise((resolve, reject) => {
    const now = new Date().toISOString();
    db.run(
      'INSERT OR REPLACE INTO user_cooldowns (ip_address, last_request) VALUES (?, ?)',
      [ipAddress, now],
      (err) => {
        if (err) return reject(err);
        console.log(`⏱️ Set cooldown for ${ipAddress} at ${now}`);
        resolve();
      }
    );
  });
};

// Request a song
app.post('/api/request', async (req, res) => {
  try {
    const { song } = req.body;
    const ipAddress = req.ip || req.connection.remoteAddress;

    // Validate song data
    if (!song || !song.id || !song.title || !song.artist) {
      return res.status(400).json({ error: 'Invalid song data' });
    }

    // Check user's current request count (max 5 songs in queue)
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
      return res.status(429).json({ error: 'You can only have 5 songs in the queue at once' });
    }

    // Check cooldown
    const canRequest = await checkCooldown(ipAddress);
    if (!canRequest) {
      return res.status(429).json({ error: 'Please wait 30 seconds between requests' });
    }

    // Check if song is already in queue
    const inQueue = await new Promise((resolve, reject) => {
      db.get(
        'SELECT id FROM queue WHERE song_id = ? AND played = 0',
        [song.id],
        (err, row) => {
          if (err) return reject(err);
          resolve(!!row);
        }
      );
    });

    if (inQueue) {
      return res.status(409).json({ error: 'This song is already in the queue' });
    }

    // Check if song was recently played (last hour)
    cleanRecentlyPlayed();
    const recentlyPlayed = await new Promise((resolve, reject) => {
      db.get(
        'SELECT id FROM recently_played WHERE song_id = ?',
        [song.id],
        (err, row) => {
          if (err) return reject(err);
          resolve(!!row);
        }
      );
    });

    if (recentlyPlayed) {
      return res.status(409).json({ error: 'This song was played recently' });
    }

    // Add to queue
    db.run(
      'INSERT INTO queue (song_id, title, artist, duration, thumbnail) VALUES (?, ?, ?, ?, ?)',
      [song.id, song.title, song.artist, song.duration, song.thumbnail || null],
      function(err) {
        if (err) {
          console.error('Queue insert error:', err);
          return res.status(500).json({ error: 'Failed to add song to queue' });
        }

        const queueId = this.lastID;

        // Track user's request
        db.run(
          'INSERT INTO user_requests (ip_address, queue_id) VALUES (?, ?)',
          [ipAddress, queueId],
          (err) => {
            if (err) {
              console.error('User request tracking error:', err);
            }
          }
        );

        // Update cooldown
        updateCooldown(ipAddress);

        // Notify all connected clients via WebSocket
        io.emit('queue_updated');

        res.json({ 
          success: true, 
          message: 'Song added to queue',
          queueId 
        });
      }
    );

  } catch (error) {
    console.error('Request error:', error);
    res.status(500).json({ error: 'Failed to process request' });
  }
});

// Mark song as played (DJ/Admin endpoint)
app.post('/api/played/:queueId', (req, res) => {
  const { queueId } = req.params;

  // Get song details before marking as played
  db.get('SELECT * FROM queue WHERE id = ?', [queueId], (err, song) => {
    if (err || !song) {
      return res.status(404).json({ error: 'Song not found in queue' });
    }

    // Mark as played in queue
    db.run('UPDATE queue SET played = 1 WHERE id = ?', [queueId], (err) => {
      if (err) {
        console.error('Mark played error:', err);
        return res.status(500).json({ error: 'Failed to mark song as played' });
      }

      // Add to recently played
      db.run(
        'INSERT INTO recently_played (song_id, title, artist) VALUES (?, ?, ?)',
        [song.song_id, song.title, song.artist],
        (err) => {
          if (err) {
            console.error('Recently played insert error:', err);
          }

          // Notify clients
          io.emit('queue_updated');
          io.emit('now_playing', {
            title: song.title,
            artist: song.artist
          });

          res.json({ success: true });
        }
      );
    });
  });
});

// Remove song from queue (DJ/Admin endpoint)
app.delete('/api/queue/:queueId', (req, res) => {
  const { queueId } = req.params;

  db.run('DELETE FROM queue WHERE id = ?', [queueId], function(err) {
    if (err) {
      console.error('Queue delete error:', err);
      return res.status(500).json({ error: 'Failed to remove song' });
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

// ==================== DEFAULT PLAYLIST MANAGEMENT ====================

// Add song to default playlist
app.post('/api/default-playlist', async (req, res) => {
  try {
    const { song } = req.body;

    if (!song || !song.id || !song.title || !song.artist) {
      return res.status(400).json({ error: 'Invalid song data' });
    }

    db.run(
      'INSERT INTO default_playlist (song_id, title, artist, duration, thumbnail) VALUES (?, ?, ?, ?, ?)',
      [song.id, song.title, song.artist, song.duration, song.thumbnail || null],
      function(err) {
        if (err) {
          console.error('Default playlist insert error:', err);
          return res.status(500).json({ error: 'Failed to add to default playlist' });
        }

        res.json({ 
          success: true, 
          message: 'Song added to default playlist',
          id: this.lastID 
        });
      }
    );
  } catch (error) {
    console.error('Default playlist error:', error);
    res.status(500).json({ error: 'Failed to process request' });
  }
});

// Get default playlist
app.get('/api/default-playlist', (req, res) => {
  db.all(
    'SELECT * FROM default_playlist ORDER BY added_at DESC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Default playlist fetch error:', err);
        return res.status(500).json({ error: 'Failed to fetch default playlist' });
      }
      res.json({ playlist: rows });
    }
  );
});

// Remove song from default playlist
app.delete('/api/default-playlist/:id', (req, res) => {
  const { id } = req.params;

  db.run('DELETE FROM default_playlist WHERE id = ?', [id], function(err) {
    if (err) {
      console.error('Default playlist delete error:', err);
      return res.status(500).json({ error: 'Failed to remove song' });
    }

    if (this.changes === 0) {
      return res.status(404).json({ error: 'Song not found' });
    }

    res.json({ success: true });
  });
});

// Get next song from default playlist (with restrictions)
const getNextDefaultSong = async () => {
  return new Promise((resolve, reject) => {
    // Get recently played song IDs
    db.all(
      'SELECT song_id FROM recently_played',
      [],
      (err, recentRows) => {
        if (err) return reject(err);

        const recentSongIds = recentRows.map(r => r.song_id);
        
        // Get songs from default playlist that haven't been played recently
        let query = 'SELECT * FROM default_playlist';
        const params = [];

        if (recentSongIds.length > 0) {
          const placeholders = recentSongIds.map(() => '?').join(',');
          query += ` WHERE song_id NOT IN (${placeholders})`;
          params.push(...recentSongIds);
        }

        query += ' ORDER BY RANDOM() LIMIT 1';

        db.get(query, params, (err, row) => {
          if (err) return reject(err);
          resolve(row);
        });
      }
    );
  });
};

// Auto-fill queue from default playlist when empty
const autoFillQueue = async () => {
  try {
    // Check if queue is empty
    const queueCount = await new Promise((resolve, reject) => {
      db.get(
        'SELECT COUNT(*) as count FROM queue WHERE played = 0',
        [],
        (err, row) => {
          if (err) return reject(err);
          resolve(row.count);
        }
      );
    });

    // If queue is empty, add a song from default playlist
    if (queueCount === 0) {
      const nextSong = await getNextDefaultSong();
      
      if (nextSong) {
        db.run(
          'INSERT INTO queue (song_id, title, artist, duration, thumbnail) VALUES (?, ?, ?, ?, ?)',
          [nextSong.song_id, nextSong.title, nextSong.artist, nextSong.duration, nextSong.thumbnail],
          (err) => {
            if (err) {
              console.error('Auto-fill error:', err);
            } else {
              console.log(`✅ Auto-filled queue with: ${nextSong.title}`);
              io.emit('queue_updated');
            }
          }
        );
      } else {
        console.log('⚠️ Default playlist is empty - cannot auto-fill');
      }
    }
  } catch (error) {
    console.error('Auto-fill queue error:', error);
  }
};

// Run auto-fill check every 10 seconds
setInterval(autoFillQueue, 10000);
// Run immediately on start
autoFillQueue();

// ==================== SETTINGS MANAGEMENT ====================

// Get settings
app.get('/api/settings', (req, res) => {
  db.get('SELECT * FROM settings WHERE id = 1', [], (err, row) => {
    if (err) {
      console.error('Settings fetch error:', err);
      return res.status(500).json({ error: 'Failed to fetch settings' });
    }
    
    if (row) {
      // Parse JSON fields
      row.allowed_genres = JSON.parse(row.allowed_genres || '["All Genres"]');
      row.colors = JSON.parse(row.colors || '{}');
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
      theme,
      explicitAllowed ? 1 : 0,
      JSON.stringify(allowedGenres),
      JSON.stringify(colors),
      eventName || '',
      customMessage || ''
    ], (err) => {
      if (err) {
        console.error('Settings update error:', err);
        return res.status(500).json({ error: 'Failed to update settings' });
      }

      console.log('✅ Settings updated');
      
      // Notify all clients that settings changed
      io.emit('settings_updated');
      
      res.json({ success: true });
    });
  } catch (error) {
    console.error('Settings update error:', error);
    res.status(500).json({ error: 'Failed to update settings' });
  }
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