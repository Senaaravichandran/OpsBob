// demo-service3 — Payment Service (port 3004)
// Bug type: CONNECTION_LEAK — responses are artificially delayed; pending requests accumulate
const http = require('http');
const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3004;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const SERVICE_NAME = 'demo-service3';

// BUG: holds live res references in an array — connection pool grows under load
const pendingRequests = [];
let totalRequests = 0;

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
  if (now - _lastWebhookAt < 10000) return;
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
  res.json({
    status: 'ok',
    pending: pendingRequests.length,
    total: totalRequests,
    uptime: process.uptime(),
  });
});

app.post('/payment', (req, res) => {
  const { userId, amount } = req.body || {};
  if (!userId || amount === undefined) {
    return res.status(400).json({ error: 'Missing userId or amount' });
  }

  totalRequests++;

  // BUG: random 0.5–3.5 s delay + storing req/res refs keeps connections open
  const delay = Math.floor(Math.random() * 3000) + 500;
  const entry = { userId, ts: Date.now(), delay, res };
  pendingRequests.push(entry);

  if (pendingRequests.length % 10 === 0) {
    console.log(`[WARN] ${pendingRequests.length} requests pending — connections accumulating`);
    if (pendingRequests.length >= 10) {
      fireWebhook({
        service: SERVICE_NAME,
        entityName: SERVICE_NAME,
        type: 'CONNECTION_LEAK',
        severity: 'HIGH',
        title: `Connection leak detected — ${pendingRequests.length} open connections`,
        message: `${pendingRequests.length} HTTP connections are being held open waiting for delayed responses.`,
      });
    }
  }

  setTimeout(() => {
    const idx = pendingRequests.indexOf(entry);
    if (idx > -1) pendingRequests.splice(idx, 1);
    const txn = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    res.json({
      transactionId: txn,
      status: 'processed',
      userId,
      amount,
      delay,
      timestamp: new Date().toISOString(),
    });
  }, delay);
});

app.get('/metrics', (req, res) => {
  res.json({
    pending: pendingRequests.length,
    total: totalRequests,
    uptime: process.uptime(),
  });
});

app.get('/', (req, res) => {
  res.json({ service: 'demo-service3', port: PORT, bug: 'CONNECTION_LEAK' });
});

app.post('/trigger-incident', (req, res) => {
  console.warn(`[INCIDENT] Manual trigger — pending=${pendingRequests.length} total=${totalRequests}`);
  fireWebhook({
    service: SERVICE_NAME,
    entityName: SERVICE_NAME,
    type: 'CONNECTION_LEAK',
    severity: 'HIGH',
    title: `CONNECTION_LEAK manually triggered on ${SERVICE_NAME}`,
    message: `${pendingRequests.length} connections currently held open (${totalRequests} total requests).`,
  });
  res.json({ ok: true, pending: pendingRequests.length, total: totalRequests });
});

app.get('/logs/stream', (req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Access-Control-Allow-Origin': '*' });
  _logBuffer.forEach(line => res.write(`data: ${JSON.stringify({ line })}\n\n`));
  _logClients.push(res);
  req.on('close', () => { const i = _logClients.indexOf(res); if (i > -1) _logClients.splice(i, 1); });
});

app.listen(PORT, () => {
  console.log(`[demo-service3] Listening on port ${PORT}`);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
