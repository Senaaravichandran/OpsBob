// demo-service2 — Payment Service (port 3003)
// Bug type: CPU_SPIKE — blocking synchronous computation on every payment request
const http = require('http');
const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3003;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const SERVICE_NAME = 'demo-service2';
let requestCount = 0;

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

// BUG: O(n²) synchronous loop — blocks the Node.js event loop entirely
function expensiveValidation(amount) {
  let result = 0;
  const n = 50000;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < 100; j++) {
      result += Math.sin(i * j) * Math.cos(amount || 1);
    }
  }
  return result > 0;
}

app.get('/health', (req, res) => {
  res.json({ status: 'ok', requests: requestCount, uptime: process.uptime() });
});

app.post('/payment', (req, res) => {
  const { userId, amount } = req.body || {};
  if (!userId || amount === undefined) {
    return res.status(400).json({ error: 'Missing userId or amount' });
  }

  requestCount++;

  // BUG: blocks event loop — all other requests stall while this runs
  const valid = expensiveValidation(amount);

  if (requestCount % 20 === 0) {
    console.log(`[WARN] CPU spike on request ${requestCount} — event loop blocked`);
    if (requestCount >= 20) {
      fireWebhook({
        service: SERVICE_NAME,
        entityName: SERVICE_NAME,
        type: 'CPU_SPIKE',
        severity: 'HIGH',
        title: `CPU spike detected — ${requestCount} blocking requests processed`,
        message: `Synchronous O(n²) validation has blocked the event loop ${requestCount} times.`,
      });
    }
  }

  const txn = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  res.json({
    transactionId: txn,
    status: 'processed',
    userId,
    amount,
    valid,
    timestamp: new Date().toISOString(),
  });
});

app.get('/metrics', (req, res) => {
  res.json({
    requests: requestCount,
    cpu_usage: process.cpuUsage(),
    uptime: process.uptime(),
  });
});

app.get('/', (req, res) => {
  res.json({ service: 'demo-service2', port: PORT, bug: 'CPU_SPIKE' });
});

app.post('/trigger-incident', (req, res) => {
  console.warn(`[INCIDENT] Manual trigger — requests=${requestCount}`);
  fireWebhook({
    service: SERVICE_NAME,
    entityName: SERVICE_NAME,
    type: 'CPU_SPIKE',
    severity: 'HIGH',
    title: `CPU_SPIKE manually triggered on ${SERVICE_NAME}`,
    message: `Blocking O(n²) validation has processed ${requestCount} requests.`,
  });
  res.json({ ok: true, requestCount });
});

app.get('/logs/stream', (req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Access-Control-Allow-Origin': '*' });
  _logBuffer.forEach(line => res.write(`data: ${JSON.stringify({ line })}\n\n`));
  _logClients.push(res);
  req.on('close', () => { const i = _logClients.indexOf(res); if (i > -1) _logClients.splice(i, 1); });
});

app.listen(PORT, () => {
  console.log(`[demo-service2] Listening on port ${PORT}`);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
