// DJ Request System - Main Server
// Complete standalone system for Raspberry Pi

const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const { Server } = require('socket.io');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

const PORT = process.env.PORT || 3000;
const MUSIC_DIR = path.join(__dirname, 'Music');
const DB_PATH = path.join(__dirname, 'data', 'requests.db');

// Ensure directories exist
if (!fs.existsSync(MUSIC_DIR)) fs.mkdirSync(MUSIC_DIR, { recursive: true });
if (!fs.existsSync(path.dirname(DB_PATH))) fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

// Initialize SQLite database
const db = new sqlite3.Database(DB_PATH, (err) => {
  if (err) {
    console.error('Error opening database:', err);
  } else {
    console.log('✅ Database connected');
    initializeDatabase();
  }
});

function initializeDatabase() {
  db.run(`
    CREATE TABLE IF NOT EXISTS requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_title TEXT NOT NULL,
      artist TEXT,
      requester_name TEXT,
      youtube_url TEXT,
      status TEXT DEFAULT 'pending',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      played_at DATETIME,
      explicit BOOLEAN DEFAULT 0,
      file_path TEXT
    )
  `, (err) => {
    if (err) console.error('Error creating table:', err);
    else console.log('✅ Database table ready');
  });

  db.run(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `, (err) => {
    if (err) console.error('Error creating settings table:', err);
    
    // Initialize default settings
    const defaults = {
      'allow_explicit': 'true',
      'theme': 'General',
      'auto_play': 'true',
      'crossfade_duration': '10'
    };
    
    for (const [key, value] of Object.entries(defaults)) {
      db.run(`INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)`, [key, value]);
    }
  });
}

// API Routes

// Get all song requests
app.get('/api/requests', (req, res) => {
  const status = req.query.status || 'pending';
  db.all(
    'SELECT * FROM requests WHERE status = ? ORDER BY created_at ASC',
    [status],
    (err, rows) => {
      if (err) {
        console.error('Error fetching requests:', err);
        res.status(500).json({ error: 'Database error' });
      } else {
        res.json(rows);
      }
    }
  );
});

// Get queue (pending requests)
app.get('/api/queue', (req, res) => {
  db.all(
    'SELECT * FROM requests WHERE status = "pending" ORDER BY created_at ASC',
    [],
    (err, rows) => {
      if (err) {
        console.error('Error fetching queue:', err);
        res.status(500).json({ error: 'Database error' });
      } else {
        res.json(rows);
      }
    }
  );
});

// Submit a new request
app.post('/api/request', (req, res) => {
  const { song_title, artist, requester_name, youtube_url } = req.body;
  
  if (!song_title) {
    return res.status(400).json({ error: 'Song title is required' });
  }
  
  db.run(
    `INSERT INTO requests (song_title, artist, requester_name, youtube_url) 
     VALUES (?, ?, ?, ?)`,
    [song_title, artist || '', requester_name || 'Anonymous', youtube_url || ''],
    function(err) {
      if (err) {
        console.error('Error inserting request:', err);
        res.status(500).json({ error: 'Failed to submit request' });
      } else {
        const newRequest = {
          id: this.lastID,
          song_title,
          artist,
          requester_name,
          youtube_url,
          status: 'pending'
        };
        
        // Notify all clients
        io.emit('new-request', newRequest);
        
        res.json({ 
          success: true, 
          message: 'Request added to queue!',
          id: this.lastID
        });
      }
    }
  );
});

// Update request status
app.patch('/api/requests/:id', (req, res) => {
  const { id } = req.params;
  const { status, file_path } = req.body;
  
  let query = 'UPDATE requests SET status = ?';
  let params = [status];
  
  if (status === 'played') {
    query += ', played_at = CURRENT_TIMESTAMP';
  }
  
  if (file_path) {
    query += ', file_path = ?';
    params.push(file_path);
  }
  
  query += ' WHERE id = ?';
  params.push(id);
  
  db.run(query, params, function(err) {
    if (err) {
      console.error('Error updating request:', err);
      res.status(500).json({ error: 'Failed to update request' });
    } else {
      io.emit('queue-update');
      res.json({ success: true });
    }
  });
});

// Delete request
app.delete('/api/requests/:id', (req, res) => {
  const { id } = req.params;
  
  db.run('DELETE FROM requests WHERE id = ?', [id], function(err) {
    if (err) {
      console.error('Error deleting request:', err);
      res.status(500).json({ error: 'Failed to delete request' });
    } else {
      io.emit('queue-update');
      res.json({ success: true });
    }
  });
});

// Get settings
app.get('/api/settings', (req, res) => {
  db.all('SELECT * FROM settings', [], (err, rows) => {
    if (err) {
      console.error('Error fetching settings:', err);
      res.status(500).json({ error: 'Database error' });
    } else {
      const settings = {};
      rows.forEach(row => {
        settings[row.key] = row.value;
      });
      res.json(settings);
    }
  });
});

// Update settings
app.post('/api/settings', (req, res) => {
  const settings = req.body;
  
  const promises = Object.entries(settings).map(([key, value]) => {
    return new Promise((resolve, reject) => {
      db.run(
        'INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
        [key, value],
        (err) => err ? reject(err) : resolve()
      );
    });
  });
  
  Promise.all(promises)
    .then(() => res.json({ success: true }))
    .catch(err => {
      console.error('Error updating settings:', err);
      res.status(500).json({ error: 'Failed to update settings' });
    });
});

// Download song
app.post('/api/download', (req, res) => {
  const { youtube_url, request_id } = req.body;
  
  if (!youtube_url) {
    return res.status(400).json({ error: 'YouTube URL is required' });
  }
  
  const sanitizeFilename = (str) => {
    return str.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  };
  
  // Generate filename
  const timestamp = Date.now();
  const outputTemplate = path.join(MUSIC_DIR, `song_${timestamp}_%(title)s.%(ext)s`);
  
  console.log(`⬇️ Downloading: ${youtube_url}`);
  
  const ytdlp = spawn('yt-dlp', [
    '-x',
    '--audio-format', 'mp3',
    '--audio-quality', '0',
    '--embed-thumbnail',
    '--add-metadata',
    '-o', outputTemplate,
    youtube_url
  ]);
  
  let downloadedFile = '';
  
  ytdlp.stdout.on('data', (data) => {
    const output = data.toString();
    console.log(output);
    
    // Try to extract the filename from yt-dlp output
    const match = output.match(/\[ExtractAudio\] Destination: (.+)/);
    if (match) {
      downloadedFile = match[1];
    }
  });
  
  ytdlp.stderr.on('data', (data) => {
    console.error('yt-dlp error:', data.toString());
  });
  
  ytdlp.on('close', (code) => {
    if (code === 0) {
      // Find the downloaded file if we don't have the exact name
      if (!downloadedFile || !fs.existsSync(downloadedFile)) {
        const files = fs.readdirSync(MUSIC_DIR)
          .filter(f => f.startsWith(`song_${timestamp}`))
          .sort((a, b) => {
            return fs.statSync(path.join(MUSIC_DIR, b)).mtime.getTime() -
                   fs.statSync(path.join(MUSIC_DIR, a)).mtime.getTime();
          });
        
        if (files.length > 0) {
          downloadedFile = path.join(MUSIC_DIR, files[0]);
        }
      }
      
      if (downloadedFile && fs.existsSync(downloadedFile)) {
        console.log(`✅ Downloaded: ${downloadedFile}`);
        
        // Update database with file path
        if (request_id) {
          db.run(
            'UPDATE requests SET file_path = ?, status = "downloaded" WHERE id = ?',
            [downloadedFile, request_id]
          );
        }
        
        io.emit('download-complete', { request_id, file_path: downloadedFile });
        res.json({ success: true, file_path: downloadedFile });
      } else {
        res.status(500).json({ error: 'Download completed but file not found' });
      }
    } else {
      res.status(500).json({ error: `Download failed with code ${code}` });
    }
  });
});

// Get audio device info
app.get('/api/audio-devices', (req, res) => {
  const aplay = spawn('aplay', ['-l']);
  let output = '';
  
  aplay.stdout.on('data', (data) => {
    output += data.toString();
  });
  
  aplay.on('close', () => {
    const devices = [];
    const lines = output.split('\n');
    
    lines.forEach(line => {
      const match = line.match(/card (\d+): (.+?) \[(.+?)\]/);
      if (match) {
        devices.push({
          card: match[1],
          name: match[2],
          description: match[3]
        });
      }
    });
    
    res.json({ devices, raw_output: output });
  });
});

// WebSocket for real-time updates
io.on('connection', (socket) => {
  console.log('🔌 Client connected');
  
  socket.on('disconnect', () => {
    console.log('🔌 Client disconnected');
  });
  
  // Send current queue on connection
  db.all('SELECT * FROM requests WHERE status = "pending" ORDER BY created_at ASC', [], (err, rows) => {
    if (!err) {
      socket.emit('queue-update', rows);
    }
  });
});

// Serve frontend
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.get('/admin', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'admin.html'));
});

// Start server
server.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('╔════════════════════════════════════════════════════════╗');
  console.log('║         🎵 DJ Request System - Server Running 🎵       ║');
  console.log('╠════════════════════════════════════════════════════════╣');
  console.log(`║  Local:   http://localhost:${PORT}                      ║`);
  console.log(`║  Network: http://192.168.4.1:${PORT}                    ║`);
  console.log('║  Admin:   /admin                                       ║');
  console.log('╚════════════════════════════════════════════════════════╝');
  console.log('');
  console.log('📁 Music directory:', MUSIC_DIR);
  console.log('💾 Database:', DB_PATH);
  console.log('');
  console.log('✅ Ready to accept song requests!');
  console.log('');
});

// Handle graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, closing database...');
  db.close(() => {
    console.log('Database closed');
    server.close(() => {
      console.log('Server closed');
      process.exit(0);
    });
  });
});
