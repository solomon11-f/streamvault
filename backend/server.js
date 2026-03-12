require('dotenv').config();
const express = require('express');
const path = require('path');
const fs = require('fs');
const cors = require('cors');
const nodemailer = require('nodemailer');

const app = express();
const PORT = Number(process.env.PORT || 3000);
const ROOT = path.resolve(__dirname, '..');
const STORE_PATH = path.join(__dirname, 'data', 'store.json');
const FRONTEND_DIR = path.join(ROOT, 'frontend');
const PUBLIC_DIR = path.join(__dirname, 'public');

app.use(cors());
app.use(express.json({ limit: '20mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(express.static(FRONTEND_DIR));
app.use(express.static(PUBLIC_DIR));

function loadStore() {
  return JSON.parse(fs.readFileSync(STORE_PATH, 'utf8'));
}

function saveStore(store) {
  fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2));
}

function genId(prefix = 'id') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeEmail(email = '') {
  return String(email || '').trim().toLowerCase();
}

function makeTransporter() {
  if (!process.env.SMTP_USER || !process.env.SMTP_PASS) return null;
  return nodemailer.createTransport({
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: Number(process.env.SMTP_PORT || 587),
    secure: String(process.env.SMTP_SECURE || 'false') === 'true',
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS
    }
  });
}

async function sendMail(to, subject, html) {
  const transporter = makeTransporter();
  if (!transporter) return { skipped: true };
  return transporter.sendMail({
    from: process.env.SMTP_FROM || process.env.SMTP_USER,
    to,
    subject,
    html
  });
}

function publicUser(user) {
  const { password, ...safe } = user;
  return safe;
}

function currentState(store) {
  return {
    settings: store.settings,
    users: store.users.map(publicUser),
    videos: store.videos
  };
}

/* ---------------------------
   HiAnime package integration
---------------------------- */
let hiAnimeScraper = null;

async function getHiAnimeScraper() {
  if (hiAnimeScraper) return hiAnimeScraper;

  // Works even if the package is ESM
  const mod = await import('aniwatch');
  if (!mod?.HiAnime?.Scraper) {
    throw new Error('aniwatch package loaded, but HiAnime.Scraper was not found');
  }

  hiAnimeScraper = new mod.HiAnime.Scraper();
  return hiAnimeScraper;
}

function normalizeProvider(provider) {
  const value = String(provider || 'hianime').trim().toLowerCase();
  if (value === 'hianime' || value === 'aniwatch') return 'hianime';
  return null;
}

function mapSearchResults(data) {
  const list = Array.isArray(data?.animes) ? data.animes : [];
  return {
    results: list.map((item) => ({
      id: item.id,
      title: item.name,
      poster: item.poster,
      type: item.type,
      rating: item.rating,
      duration: item.duration,
      episodes: item.episodes || {},
      url: item.id
    }))
  };
}

function mapEpisodes(data, animeId) {
  const list = Array.isArray(data?.episodes) ? data.episodes : [];
  return {
    animeId,
    totalEpisodes: data?.totalEpisodes || list.length,
    episodes: list.map((ep) => ({
      number: ep.number,
      title: ep.title || `Episode ${ep.number}`,
      episodeId: ep.episodeId,
      url: ep.episodeId,
      isFiller: !!ep.isFiller
    }))
  };
}

/* ---------------------------
   Existing app routes
---------------------------- */

app.get('/api/bootstrap', (req, res) => {
  const store = loadStore();
  res.json(currentState(store));
});

app.get('/api/auth/session/:id', (req, res) => {
  const store = loadStore();
  const user = store.users.find(u => u.id === req.params.id);
  if (!user) return res.status(404).json({ error: 'Session not found' });
  res.json({ user: publicUser(user) });
});

app.post('/api/auth/login', (req, res) => {
  const store = loadStore();
  const email = normalizeEmail(req.body.email);
  const password = String(req.body.password || '');
  const user = store.users.find(u => normalizeEmail(u.email) === email && u.password === password);
  if (!user) return res.status(400).json({ error: 'Invalid email or password' });
  if (!user.verified) return res.status(400).json({ error: 'Please verify your email first' });
  if (user.status === 'pending') return res.status(400).json({ error: 'Awaiting admin approval' });
  if (user.status === 'rejected') return res.status(400).json({ error: 'Account request declined' });
  res.json({ user: publicUser(user), state: currentState(store) });
});

app.post('/api/auth/signup', async (req, res) => {
  const store = loadStore();
  const firstName = String(req.body.firstName || '').trim();
  const lastName = String(req.body.lastName || '').trim();
  const email = normalizeEmail(req.body.email);
  const password = String(req.body.password || '');
  if (!firstName || !email || !password) return res.status(400).json({ error: 'Fill in required fields' });
  if (password.length < 8) return res.status(400).json({ error: 'Password min. 8 characters' });
  if (store.users.some(u => normalizeEmail(u.email) === email)) return res.status(400).json({ error: 'Email already registered' });

  const code = String(Math.floor(100000 + Math.random() * 900000));
  const pending = {
    id: genId('verify'),
    firstName,
    lastName,
    email,
    password,
    code,
    createdAt: new Date().toISOString()
  };

  store.pendingVerifications = store.pendingVerifications.filter(v => normalizeEmail(v.email) !== email);
  store.pendingVerifications.push(pending);
  saveStore(store);

  try {
    await sendMail(
      email,
      'StreamVault verification code',
      `<p>Your verification code is:</p><h2>${code}</h2><p>After verification, your account will wait for admin approval.</p>`
    );
  } catch (err) {
    console.error('Mail send failed:', err.message);
  }

  const devCode = !process.env.SMTP_USER ? code : undefined;
  res.json({
    ok: true,
    message: process.env.SMTP_USER ? 'Verification code sent' : `SMTP not configured. Dev code: ${code}`,
    devCode
  });
});

app.post('/api/auth/verify', async (req, res) => {
  const store = loadStore();
  const email = normalizeEmail(req.body.email);
  const code = String(req.body.code || '').trim();
  const pending = store.pendingVerifications.find(v => normalizeEmail(v.email) === email && String(v.code) === code);
  if (!pending) return res.status(400).json({ error: 'Invalid verification code' });

  const user = {
    id: genId('u'),
    email: pending.email,
    password: pending.password,
    firstName: pending.firstName,
    lastName: pending.lastName,
    role: 'user',
    status: 'pending',
    verified: true,
    joined: new Date().toISOString()
  };

  store.users.push(user);
  store.pendingVerifications = store.pendingVerifications.filter(v => v.id !== pending.id);
  saveStore(store);

  try {
    await sendMail(email, 'StreamVault request received', `<p>Hi ${user.firstName}, your account is verified and now waiting for admin approval.</p>`);
  } catch (err) {
    console.error('Mail send failed:', err.message);
  }

  res.json({ ok: true, user: publicUser(user), state: currentState(store) });
});

app.post('/api/admin/user-status', async (req, res) => {
  const store = loadStore();
  const { id, status } = req.body || {};
  const user = store.users.find(u => u.id === id);
  if (!user) return res.status(404).json({ error: 'User not found' });

  user.status = status;
  saveStore(store);

  try {
    if (status === 'approved') {
      await sendMail(user.email, 'StreamVault account approved', `<p>Your StreamVault account has been approved. You can log in now.</p>`);
    } else if (status === 'rejected') {
      await sendMail(user.email, 'StreamVault account update', `<p>Your StreamVault request was declined.</p>`);
    }
  } catch (err) {
    console.error('Mail send failed:', err.message);
  }

  res.json({ ok: true, user: publicUser(user), state: currentState(store) });
});

app.post('/api/settings', (req, res) => {
  const store = loadStore();
  const { entryCode, adminPassword } = req.body || {};

  if (entryCode && /^\d{4}$/.test(entryCode)) store.settings.entryCode = entryCode;

  if (adminPassword) {
    const admin = store.users.find(u => u.role === 'admin');
    if (admin) admin.password = String(adminPassword);
  }

  saveStore(store);
  res.json({ ok: true, state: currentState(store) });
});

app.post('/api/videos/sync', (req, res) => {
  const store = loadStore();
  const videos = Array.isArray(req.body.videos) ? req.body.videos : null;
  if (!videos) return res.status(400).json({ error: 'videos must be an array' });

  store.videos = videos;
  saveStore(store);
  res.json({ ok: true, count: store.videos.length });
});

/* ---------------------------
   NEW: search / episodes / extract
---------------------------- */

app.get('/api/provider-search', async (req, res) => {
  const q = String(req.query.q || '').trim();
  const provider = normalizeProvider(req.query.provider);

  if (!q) return res.status(400).json({ error: 'Missing q' });
  if (!provider) return res.status(400).json({ error: 'Unsupported provider' });

  try {
    const hi = await getHiAnimeScraper();
    const data = await hi.search(q);
    res.json(mapSearchResults(data));
  } catch (err) {
    console.error('provider-search failed:', err);
    res.status(500).json({
      error: 'Provider search failed',
      details: err?.message || 'Unknown error'
    });
  }
});

app.get('/api/provider-episodes', async (req, res) => {
  const url = String(req.query.url || '').trim();
  const provider = normalizeProvider(req.query.provider);

  if (!url) return res.status(400).json({ error: 'Missing url' });
  if (!provider) return res.status(400).json({ error: 'Unsupported provider' });

  try {
    const hi = await getHiAnimeScraper();
    const animeId = url; // frontend passes the anime id here
    const data = await hi.getEpisodes(animeId);
    res.json(mapEpisodes(data, animeId));
  } catch (err) {
    console.error('provider-episodes failed:', err);
    res.status(500).json({
      error: 'Episode fetch failed',
      details: err?.message || 'Unknown error'
    });
  }
});

app.post('/api/extract', async (req, res) => {
  const episodeId = String(req.body.url || '').trim();
  const server = String(req.body.server || 'vidstreaming').trim();
  const category = String(req.body.category || 'sub').trim().toLowerCase();

  if (!episodeId) return res.status(400).json({ error: 'Missing url' });

  try {
    const hi = await getHiAnimeScraper();

    // optional: validate available servers first
    let selectedServer = server;
    try {
      const serverData = await hi.getEpisodeServers(episodeId);
      const pool = Array.isArray(serverData?.[category]) ? serverData[category] : [];
      if (pool.length && !pool.some(s => s.serverName === selectedServer || s.serverId === selectedServer)) {
        selectedServer = pool[0].serverName;
      }
    } catch (_) {
      // if server lookup fails, just continue with the requested/default server
    }

    const data = await hi.getEpisodeSources(episodeId, selectedServer, category);

    res.json({
      stream: Array.isArray(data?.sources) && data.sources.length ? data.sources[0].url : null,
      sources: data?.sources || [],
      subtitles: data?.subtitles || [],
      headers: data?.headers || {},
      anilistID: data?.anilistID ?? null,
      malID: data?.malID ?? null,
      server: selectedServer,
      category
    });
  } catch (err) {
    console.error('extract failed:', err);
    res.status(500).json({
      error: 'Extraction failed',
      details: err?.message || 'Unknown error'
    });
  }
});

app.get('/api/health', async (req, res) => {
  res.json({
    ok: true,
    scraper: 'aniwatch-package',
    mode: 'direct-node-integration'
  });
});

app.get('*', (req, res) => {
  res.sendFile(path.join(FRONTEND_DIR, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`StreamVault backend running on http://localhost:${PORT}`);
});