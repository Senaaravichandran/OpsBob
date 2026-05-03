# Root Cause Analysis: INC-DEMO-SER-1777808149052

## Incident Summary
- **Service**: demo-service3
- **Incident ID**: INC-DEMO-SER-1777808149052
- **Type**: CONNECTION_LEAK
- **Severity**: HIGH
- **Detection**: Memory growth of 0MB over 10 minutes

## Root Cause Identification

### Exact Location
- **File**: `demo-service3/server.js`
- **Variable**: `pendingRequests`
- **Line**: 13
- **Declaration**: `const pendingRequests = [];`

### Technical Analysis

The `pendingRequests` array stores objects containing live HTTP response references:

```javascript
const entry = { userId, ts: Date.now(), delay, res };
pendingRequests.push(entry);
```

**Critical Flaw**: When a client connection is aborted, times out, or fails before the `setTimeout` callback executes, the response object remains in the array indefinitely. This prevents garbage collection of:
- The response object (`res`)
- Associated socket connections
- Request buffers and headers
- Any closures or event listeners attached to the connection

The cleanup logic only executes inside the `setTimeout` callback:

```javascript
setTimeout(() => {
  const idx = pendingRequests.indexOf(entry);
  if (idx > -1) pendingRequests.splice(idx, 1);
  // ... send response
}, delay);
```

If the connection closes before this timeout fires (client disconnect, network failure, load balancer timeout), the entry is never removed, causing unbounded memory growth under production load.

## Fix Plan

1. **Add connection close listener**: Attach a `'close'` event handler to each response object immediately after pushing to `pendingRequests`. When the connection closes prematurely, remove the entry from the array and clear the associated timeout to prevent attempting to write to a closed socket.

2. **Store timeout IDs for cleanup**: Modify the entry structure to include the timeout ID (`{ userId, ts, delay, res, timeoutId }`). This enables explicit cleanup via `clearTimeout()` when connections close, preventing orphaned timers that reference dead connections.

3. **Implement defensive response writing**: Wrap the `res.json()` call in a try-catch block and check `res.writableEnded` before attempting to write. This prevents crashes when the timeout fires after a connection has already closed, ensuring graceful degradation under network instability.

## Corrected Implementation

```javascript
// demo-service3 — Payment Service (port 3004)
// FIXED: Proper connection lifecycle management with close event handling
const http = require('http');
const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3004;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const SERVICE_NAME = 'demo-service3';

// FIXED: Now properly cleaned up when connections close
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

  const delay = Math.floor(Math.random() * 3000) + 500;
  const entry = { userId, ts: Date.now(), delay, res, timeoutId: null };
  pendingRequests.push(entry);

  // FIX 1: Add connection close listener for premature cleanup
  const cleanupEntry = () => {
    const idx = pendingRequests.indexOf(entry);
    if (idx > -1) {
      if (entry.timeoutId) {
        clearTimeout(entry.timeoutId);
      }
      pendingRequests.splice(idx, 1);
      console.log(`[CLEANUP] Removed entry for userId=${userId}, pending=${pendingRequests.length}`);
    }
  };

  res.on('close', () => {
    if (!res.writableEnded) {
      console.log(`[CLOSE] Connection closed prematurely for userId=${userId}`);
      cleanupEntry();
    }
  });

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

  // FIX 2: Store timeout ID for explicit cleanup
  entry.timeoutId = setTimeout(() => {
    cleanupEntry();
    const txn = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // FIX 3: Defensive response writing
    try {
      if (!res.writableEnded) {
        res.json({
          transactionId: txn,
          status: 'processed',
          userId,
          amount,
          delay,
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error(`[ERROR] Failed to send response for userId=${userId}: ${err.message}`);
    }
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
  res.json({ service: 'demo-service3', port: PORT, bug: 'CONNECTION_LEAK (FIXED)' });
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
```

## Regression Test

```javascript
// test/connection-leak.test.js
// Regression test for INC-DEMO-SER-1777808149052
const request = require('supertest');
const http = require('http');

describe('Connection Leak Regression Test', () => {
  let app;
  let server;

  beforeEach(() => {
    // Import fresh instance for each test
    delete require.cache[require.resolve('../server')];
    app = require('../server');
  });

  afterEach((done) => {
    if (server) {
      server.close(done);
    } else {
      done();
    }
  });

  test('should clean up pendingRequests when client aborts connection', (done) => {
    // Start server
    server = app.listen(0);
    const port = server.address().port;

    // Make request and abort it immediately
    const req = http.request({
      hostname: 'localhost',
      port: port,
      path: '/payment',
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    req.write(JSON.stringify({ userId: 'test-user', amount: 100 }));
    
    // Abort connection after 100ms (before timeout fires)
    setTimeout(() => {
      req.destroy();
    }, 100);

    // Wait for cleanup to occur
    setTimeout(async () => {
      // Check metrics to verify cleanup happened
      const response = await request(app).get('/metrics');
      
      // pendingRequests should be 0 after cleanup
      expect(response.body.pending).toBe(0);
      expect(response.body.total).toBe(1);
      
      done();
    }, 500);
  });

  test('should not accumulate entries when multiple connections abort', (done) => {
    server = app.listen(0);
    const port = server.address().port;

    const abortedRequests = 10;
    let completed = 0;

    // Create multiple requests and abort them
    for (let i = 0; i < abortedRequests; i++) {
      const req = http.request({
        hostname: 'localhost',
        port: port,
        path: '/payment',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      req.write(JSON.stringify({ userId: `user-${i}`, amount: 100 }));
      
      setTimeout(() => {
        req.destroy();
        completed++;
      }, 50 + i * 10);
    }

    // Verify cleanup after all aborts
    setTimeout(async () => {
      expect(completed).toBe(abortedRequests);
      
      const response = await request(app).get('/metrics');
      
      // All entries should be cleaned up
      expect(response.body.pending).toBe(0);
      expect(response.body.total).toBe(abortedRequests);
      
      done();
    }, 1000);
  });

  test('should handle normal completion without leaks', (done) => {
    server = app.listen(0);
    const port = server.address().port;

    // Make normal request that completes
    request(app)
      .post('/payment')
      .send({ userId: 'test-user', amount: 100 })
      .expect(200)
      .end(async (err) => {
        if (err) return done(err);

        // Wait for timeout to complete
        setTimeout(async () => {
          const response = await request(app).get('/metrics');
          
          // Should be cleaned up after completion
          expect(response.body.pending).toBe(0);
          expect(response.body.total).toBe(1);
          
          done();
        }, 4000); // Max delay is 3500ms
      });
  });
});
```

## Verification Steps

1. **Deploy the fixed code** to demo-service3
2. **Run the regression test suite** to verify the fix
3. **Monitor metrics endpoint** (`/metrics`) under load to confirm `pending` count returns to 0
4. **Simulate connection aborts** using load testing tools (e.g., `ab -c 100 -n 1000` with early termination)
5. **Verify memory stability** over 24-hour period with production traffic patterns

## Prevention Measures

1. **Code review checklist**: Always attach cleanup handlers to long-lived connections
2. **Monitoring**: Alert on `pendingRequests.length` exceeding threshold for >5 minutes
3. **Load testing**: Include connection abort scenarios in CI/CD pipeline
4. **Linting rule**: Enforce event listener cleanup for response objects

---

**Analysis completed**: 2026-05-03T11:37:00Z  
**Analyst**: Bob Shell (OpsBob AI)
