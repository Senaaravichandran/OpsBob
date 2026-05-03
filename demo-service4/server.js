// demo-service4 — Payment Service (port 3005)
// Clean working implementation — bounded cache, proper validation, no blocking ops
const http = require('http');
const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3005;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const SERVICE_NAME = 'demo-service4';

// --- Log capture & SSE stream ---
const _logClients = [];
const _logBuffer = [];
const MAX_LOG = 500;
function _pushLog(line) {
  _logBuffer.push(line);
  if (_logBuffer.length > MAX_LOG) _logBuffer.shift();
  _logClients.forEach(r => { try { r.write(`data: ${JSON.stringify({ line })}\n\n`); } catch {} });
}
const _origLog = console.log.bind(console);
const _origWarn = console.warn.bind(console);
const _origError = console.error.bind(console);
console.log = (...a) => { const s = a.join(' '); _origLog(s); _pushLog(s); };
console.warn = (...a) => { const s = a.join(' '); _origWarn(s); _pushLog(s); };
console.error = (...a) => { const s = a.join(' '); _origError(s); _pushLog(s); };

const MAX_CACHE = 500;
const CACHE_TTL_MS = 60 * 1000; // 1 minute

// Clean: bounded Map with TTL eviction
const recentTxns = new Map();

function evictStale() {
  const cutoff = Date.now() - CACHE_TTL_MS;
  for (const [key, val] of recentTxns) {
    if (val.ts < cutoff) recentTxns.delete(key);
  }
  if (recentTxns.size > MAX_CACHE) {
    const oldest = recentTxns.keys().next().value;
    recentTxns.delete(oldest);
  }
}

app.get('/health', (req, res) => {
  const mem = process.memoryUsage();
  res.json({
    status: 'ok',
    cacheSize: recentTxns.size,
    heapUsed: `${Math.round(mem.heapUsed / 1024 / 1024)}MB`,
    uptime: process.uptime(),
  });
});

app.post('/payment', (req, res) => {
  const { userId, amount } = req.body || {};
  if (!userId || typeof amount !== 'number' || amount <= 0) {
    return res.status(400).json({
      error: 'Invalid request: userId and positive numeric amount required',
    });
  }

  const txn = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  evictStale();
  recentTxns.set(txn, { userId, amount, ts: Date.now() });

  res.json({
    transactionId: txn,
    status: 'processed',
    userId,
    amount,
    timestamp: new Date().toISOString(),
  });
});

app.get('/metrics', (req, res) => {
  const mem = process.memoryUsage();
  res.json({
    cache_size: recentTxns.size,
    heap_mb: Math.round(mem.heapUsed / 1024 / 1024),
    uptime: process.uptime(),
  });
});

app.get('/', (req, res) => {
  res.json({ service: 'demo-service4', port: PORT, status: 'healthy' });
});

app.post('/trigger-incident', (req, res) => {
  // Clean service — no real bug, but we can still manually report a nominal webhook
  console.log(`[INFO] trigger-incident called on clean service — no anomaly detected`);
  res.json({ ok: true, status: 'nominal', cacheSize: recentTxns.size });
});

app.get('/logs/stream', (req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Access-Control-Allow-Origin': '*' });
  _logBuffer.forEach(line => res.write(`data: ${JSON.stringify({ line })}\n\n`));
  _logClients.push(res);
  req.on('close', () => { const i = _logClients.indexOf(res); if (i > -1) _logClients.splice(i, 1); });
});

app.listen(PORT, () => {
  console.log(`[demo-service4] Listening on port ${PORT}`);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
