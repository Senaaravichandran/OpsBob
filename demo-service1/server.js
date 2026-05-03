// demo-service1 — Payment Service (port 3002)
// Bug type: MEMORY_LEAK — sessionCache grows without bound, never evicted
const http = require('http');
const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3002;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const SERVICE_NAME = 'demo-service1';

// BUG: plain Map that is never cleared — every payment adds an entry forever
const sessionCache = new Map();

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

// --- Webhook helper ---
let _lastWebhookAt = 0;
function fireWebhook(payload) {
  const now = Date.now();
  if (now - _lastWebhookAt < 10000) return; // debounce 10s
  _lastWebhookAt = now;
  const body = JSON.stringify(payload);
  const url = new URL('/webhook', BACKEND_URL);
  const req = http.request({ hostname: url.hostname, port: url.port || 80, path: url.pathname, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, res => {
    console.log(`[WEBHOOK] Fired → ${res.statusCode}`);
  });
  req.on('error', e => console.error(`[WEBHOOK] Failed: ${e.message}`));
  req.write(body);
  req.end();
}

app.get('/health', (req, res) => {
  const mem = process.memoryUsage();
  res.json({
    status: 'ok',
    cacheSize: sessionCache.size,
    heapUsed: `${Math.round(mem.heapUsed / 1024 / 1024)}MB`,
    uptime: process.uptime(),
  });
});

app.post('/payment', (req, res) => {
  const { userId, amount } = req.body || {};
  if (!userId || amount === undefined) {
    return res.status(400).json({ error: 'Missing userId or amount' });
  }

  const txn = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  // BUG: full request context stored; never evicted
  sessionCache.set(txn, {
    userId,
    amount,
    ts: Date.now(),
    headers: req.headers,
    ip: req.ip,
  });

  if (sessionCache.size % 100 === 0) {
    const mb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
    console.log(`[WARN] cache=${sessionCache.size} entries heap=${mb}MB`);
    if (sessionCache.size >= 200) {
      fireWebhook({
        service: SERVICE_NAME,
        entityName: SERVICE_NAME,
        type: 'MEMORY_LEAK',
        severity: 'HIGH',
        title: `Memory leak detected — ${sessionCache.size} cache entries`,
        message: `Unbounded sessionCache has grown to ${sessionCache.size} entries (${mb}MB heap).`,
      });
    }
  }

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
    cache_size: sessionCache.size,
    heap_mb: Math.round(mem.heapUsed / 1024 / 1024),
    uptime: process.uptime(),
  });
});

app.get('/', (req, res) => {
  res.json({ service: 'demo-service1', port: PORT, bug: 'MEMORY_LEAK' });
});

app.post('/trigger-incident', (req, res) => {
  const mb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
  console.warn(`[INCIDENT] Manual trigger — cache=${sessionCache.size} heap=${mb}MB`);
  fireWebhook({
    service: SERVICE_NAME,
    entityName: SERVICE_NAME,
    type: 'MEMORY_LEAK',
    severity: 'HIGH',
    title: `MEMORY_LEAK manually triggered on ${SERVICE_NAME}`,
    message: `sessionCache has ${sessionCache.size} entries using ${mb}MB of heap.`,
  });
  res.json({ ok: true, cacheSize: sessionCache.size, heapMB: mb });
});

app.get('/logs/stream', (req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Access-Control-Allow-Origin': '*' });
  _logBuffer.forEach(line => res.write(`data: ${JSON.stringify({ line })}\n\n`));
  _logClients.push(res);
  req.on('close', () => { const i = _logClients.indexOf(res); if (i > -1) _logClients.splice(i, 1); });
});

app.listen(PORT, () => {
  console.log(`[demo-service1] Listening on port ${PORT}`);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
