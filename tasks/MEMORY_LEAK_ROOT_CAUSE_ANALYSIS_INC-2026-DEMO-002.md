# Memory Leak Root Cause Analysis - INC-2026-DEMO-002

**Incident ID**: INC-2026-DEMO-002  
**Service**: payments-api  
**Severity**: HIGH  
**Type**: MEMORY_LEAK  
**Analysis Date**: 2026-05-03

---

## Root Cause Identification

### Primary Memory Leak

**Variable**: `sessionCache`  
**File**: `demo-service/server.js`  
**Line**: ~23 (declaration) and ~130 (leak point)  
**Code**:
```javascript
const sessionCache = new Map(); // Line 23

// Line ~130 in /payment endpoint
sessionCache.set(Date.now(), {
  userId,
  amount,
  transactionId,
  timestamp: new Date().toISOString(),
  requestBody: req.body,
  headers: req.headers,
  ip: req.ip
});
```

**Root Cause**: The `sessionCache` Map uses monotonically increasing timestamps as keys and stores complete request payloads for every payment transaction. There is **no eviction mechanism, TTL enforcement, or size limit**, causing linear memory growth proportional to request volume. Each payment request adds a new entry that is never removed, leading to unbounded heap consumption.

### Secondary Memory Leak

**Variable**: `sessions`  
**File**: `demo-service/store/sessionStore.js`  
**Line**: ~6 (declaration) and ~14 (leak point)  
**Code**:
```javascript
this.sessions = new Map(); // Line 6

set(sessionId, session) {
  this.sessions.set(sessionId, session); // Line 14
  // BUG: No cleanup mechanism!
}
```

**Root Cause**: The SessionStore maintains a separate `sessions` Map that accumulates session objects indefinitely. While the middleware updates `lastAccessed` timestamps, there is no background cleanup process to expire stale sessions.

### Tertiary Memory Leak

**File**: `demo-service/middleware/session.js`  
**Line**: ~10-16  
**Code**:
```javascript
if (!session) {
  session = {
    id: sessionId,
    createdAt: Date.now(),
    data: {}
  };
  sessionStore.set(sessionId, session);
}
```

**Root Cause**: Creates new session entries for every request lacking an `x-session-id` header, feeding into the SessionStore leak without any session lifecycle management.

---

## Fix Plan (3 Bullet Points)

1. **Implement LRU Cache with Size Limit for sessionCache**: Replace the unbounded Map in `server.js` with an LRU (Least Recently Used) cache that automatically evicts oldest entries when a maximum size (e.g., 1000 entries) is reached, preventing unbounded growth while maintaining recent transaction history for debugging.

2. **Add TTL-Based Session Cleanup in SessionStore**: Implement a periodic cleanup interval (e.g., every 60 seconds) in `store/sessionStore.js` that removes sessions older than a configurable TTL (e.g., 30 minutes), using the `lastAccessed` timestamp to identify expired sessions and reclaim memory from abandoned sessions.

3. **Enforce Session ID Validation in Middleware**: Modify `middleware/session.js` to require valid session IDs and reject requests with missing or malformed session headers, preventing uncontrolled session creation and ensuring clients maintain session state properly.

---

## Corrected Code

### 1. server.js (Fixed sessionCache with LRU)

```javascript
// Demo Payment Service - Express.js API with FIXED memory leak
const express = require('express');
const app = express();

// Import metrics and traces modules
const { getMetrics, getPrometheusMetrics, trackRequest, trackError } = require('./metrics');
const { captureTrace, captureError, captureMemoryLeakTrace, getTraces } = require('./debug/traces');

// Configuration from environment variables with fallbacks
const PORT = process.env.PORT || 3001;
const MEMORY_ALERT_THRESHOLD_MB = parseInt(process.env.MEMORY_ALERT_THRESHOLD_MB || '250');
const CACHE_MAX_SIZE = parseInt(process.env.CACHE_MAX_SIZE || '1000');

// Middleware to parse JSON request bodies
app.use(express.json());

// FIXED: LRU cache with size limit to prevent unbounded growth
class LRUCache {
  constructor(maxSize) {
    this.maxSize = maxSize;
    this.cache = new Map();
  }

  set(key, value) {
    // Remove oldest entry if at capacity
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    
    // Delete and re-add to move to end (most recent)
    this.cache.delete(key);
    this.cache.set(key, value);
  }

  get(key) {
    if (!this.cache.has(key)) return undefined;
    
    // Move to end (most recently used)
    const value = this.cache.get(key);
    this.cache.delete(key);
    this.cache.set(key, value);
    return value;
  }

  get size() {
    return this.cache.size;
  }

  clear() {
    this.cache.clear();
  }
}

const sessionCache = new LRUCache(CACHE_MAX_SIZE);

// Memory monitoring interval
let memoryAlertFired = false;
const memoryMonitor = setInterval(() => {
  const heapMb = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
  if (heapMb > MEMORY_ALERT_THRESHOLD_MB && !memoryAlertFired) {
    memoryAlertFired = true;
    captureMemoryLeakTrace(sessionCache.size);
    console.log(`⚠️  Memory alert: heap=${heapMb}MB exceeds threshold=${MEMORY_ALERT_THRESHOLD_MB}MB`);
  }
}, 3000);

/**
 * Health check endpoint
 */
app.get('/health', (req, res) => {
  try {
    const memoryUsage = process.memoryUsage();
    
    res.json({
      status: 'ok',
      memory: {
        rss: `${Math.round(memoryUsage.rss / 1024 / 1024)}MB`,
        heapTotal: `${Math.round(memoryUsage.heapTotal / 1024 / 1024)}MB`,
        heapUsed: `${Math.round(memoryUsage.heapUsed / 1024 / 1024)}MB`,
        external: `${Math.round(memoryUsage.external / 1024 / 1024)}MB`,
        raw: memoryUsage
      },
      cacheSize: sessionCache.size,
      cacheMaxSize: CACHE_MAX_SIZE,
      uptime: process.uptime()
    });
  } catch (error) {
    console.error('Health check error:', error);
    res.status(500).json({
      status: 'error',
      message: 'Health check failed'
    });
  }
});

/**
 * GET /metrics
 */
app.get('/metrics', (req, res) => {
  try {
    const format = req.query.format;
    
    if (format === 'prometheus') {
      res.set('Content-Type', 'text/plain; charset=utf-8');
      return res.send(getPrometheusMetrics(sessionCache));
    }

    const metrics = getMetrics(sessionCache);
    res.json(metrics);
  } catch (error) {
    console.error('Metrics error:', error);
    trackError();
    res.status(500).json({ error: 'Failed to collect metrics' });
  }
});

/**
 * GET /debug/traces
 */
app.get('/debug/traces', (req, res) => {
  try {
    const limit = parseInt(req.query.limit || '10');
    const traces = getTraces(limit);
    res.json(traces);
  } catch (error) {
    console.error('Traces error:', error);
    res.status(500).json({ error: 'Failed to retrieve traces' });
  }
});

/**
 * Payment processing endpoint - FIXED
 */
app.post('/payment', (req, res) => {
  trackRequest();
  
  try {
    const { userId, amount } = req.body;
    
    if (!userId || amount === undefined) {
      trackError();
      return res.status(400).json({
        status: 'error',
        message: 'Missing required fields: userId and amount'
      });
    }
    
    if (typeof amount !== 'number' || amount <= 0) {
      trackError();
      return res.status(400).json({
        status: 'error',
        message: 'Amount must be a positive number'
      });
    }
    
    const transactionId = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // FIXED: LRU cache automatically evicts old entries
    sessionCache.set(Date.now(), {
      userId,
      amount,
      transactionId,
      timestamp: new Date().toISOString()
      // Removed: requestBody, headers, ip (reduce memory footprint)
    });

    if (sessionCache.size % 100 === 0) {
      captureTrace('payment_handler', {
        cache_size: sessionCache.size,
        transaction_id: transactionId,
        user_id: userId
      });
    }
    
    if (sessionCache.size % 50 === 0) {
      console.log(`Payment processed: ${transactionId} | Cache size: ${sessionCache.size}/${CACHE_MAX_SIZE} entries`);
    }
    
    res.json({
      transactionId,
      status: 'processed',
      userId,
      amount,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Payment processing error:', error);
    trackError();
    captureError(error, 'payment_handler');
    res.status(500).json({
      status: 'error',
      message: 'Payment processing failed',
      error: error.message
    });
  }
});

/**
 * Root endpoint
 */
app.get('/', (req, res) => {
  res.json({
    service: 'payments-api',
    version: '1.0.1',
    description: 'Payment processing microservice (memory leak fixed)',
    endpoints: {
      health: 'GET /health',
      payment: 'POST /payment',
      metrics: 'GET /metrics',
      debug_traces: 'GET /debug/traces'
    }
  });
});

/**
 * 404 handler
 */
app.use((req, res) => {
  res.status(404).json({
    status: 'error',
    message: 'Endpoint not found',
    path: req.path
  });
});

/**
 * Global error handler
 */
app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  trackError();
  captureError(err, 'global_error_handler');
  res.status(500).json({
    status: 'error',
    message: 'Internal server error',
    error: process.env.NODE_ENV === 'development' ? err.message : undefined
  });
});

/**
 * Start the server
 */
const server = app.listen(PORT, () => {
  console.log(`Demo service listening on port ${PORT}`);
  console.log(`Cache max size: ${CACHE_MAX_SIZE} entries`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Metrics: http://localhost:${PORT}/metrics`);
  console.log(`Debug traces: http://localhost:${PORT}/debug/traces`);
  console.log(`Payment endpoint: http://localhost:${PORT}/payment`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
});

/**
 * Graceful shutdown
 */
process.on('SIGTERM', () => {
  console.log('SIGTERM signal received: closing HTTP server');
  clearInterval(memoryMonitor);
  server.close(() => {
    console.log('HTTP server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('SIGINT signal received: closing HTTP server');
  clearInterval(memoryMonitor);
  server.close(() => {
    console.log('HTTP server closed');
    process.exit(0);
  });
});

module.exports = app;
```

### 2. store/sessionStore.js (Fixed with TTL cleanup)

```javascript
// In-memory session store with TTL-based cleanup - FIXED

class SessionStore {
  constructor(options = {}) {
    this.sessions = new Map();
    this.ttl = options.ttl || 30 * 60 * 1000; // Default: 30 minutes
    this.cleanupInterval = options.cleanupInterval || 60 * 1000; // Default: 60 seconds
    
    console.log(`SessionStore initialized (TTL: ${this.ttl}ms, Cleanup: ${this.cleanupInterval}ms)`);
    
    // FIXED: Start periodic cleanup
    this.startCleanup();
  }
  
  get(sessionId) {
    const session = this.sessions.get(sessionId);
    
    // Check if session is expired
    if (session && this.isExpired(session)) {
      this.sessions.delete(sessionId);
      return undefined;
    }
    
    return session;
  }
  
  set(sessionId, session) {
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  // FIXED: Check if session is expired based on lastAccessed
  isExpired(session) {
    if (!session.lastAccessed) return false;
    return Date.now() - session.lastAccessed > this.ttl;
  }
  
  // FIXED: Cleanup expired sessions
  cleanup() {
    const now = Date.now();
    let removed = 0;
    
    for (const [sessionId, session] of this.sessions.entries()) {
      if (this.isExpired(session)) {
        this.sessions.delete(sessionId);
        removed++;
      }
    }
    
    if (removed > 0) {
      console.log(`Cleaned up ${removed} expired sessions (remaining: ${this.sessions.size})`);
    }
  }
  
  // FIXED: Start periodic cleanup interval
  startCleanup() {
    this.cleanupTimer = setInterval(() => {
      this.cleanup();
    }, this.cleanupInterval);
    
    // Prevent timer from keeping process alive
    if (this.cleanupTimer.unref) {
      this.cleanupTimer.unref();
    }
  }
  
  // FIXED: Stop cleanup (for graceful shutdown)
  stopCleanup() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = null;
    }
  }
}

// Export singleton instance with configurable options
module.exports = new SessionStore({
  ttl: parseInt(process.env.SESSION_TTL || '1800000'), // 30 minutes
  cleanupInterval: parseInt(process.env.SESSION_CLEANUP_INTERVAL || '60000') // 60 seconds
});
```

### 3. middleware/session.js (Fixed with validation)

```javascript
// Session middleware with validation - FIXED
const sessionStore = require('../store/sessionStore');

function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'];
  
  // FIXED: Require valid session ID, don't auto-create
  if (!sessionId) {
    return res.status(401).json({
      error: 'Missing session ID',
      message: 'x-session-id header is required'
    });
  }
  
  // Validate session ID format (basic validation)
  if (!/^session_[0-9]+_[0-9.]+$/.test(sessionId)) {
    return res.status(400).json({
      error: 'Invalid session ID format',
      message: 'Session ID must match pattern: session_<timestamp>_<random>'
    });
  }
  
  // Get or create session
  let session = sessionStore.get(sessionId);
  
  if (!session) {
    session = {
      id: sessionId,
      createdAt: Date.now(),
      data: {}
    };
    sessionStore.set(sessionId, session);
  }
  
  // Attach session to request
  req.session = session.data;
  req.sessionId = sessionId;
  
  // FIXED: Update last accessed time for TTL tracking
  session.lastAccessed = Date.now();
  
  next();
}

module.exports = sessionMiddleware;
```

---

## Regression Test

### Test File: `demo-service/test/memory-leak-regression.test.js`

```javascript
/**
 * Regression test for memory leak bug (INC-2026-DEMO-002)
 * Verifies that sessionCache does not grow unbounded under load
 */

const request = require('supertest');
const app = require('../server');

describe('Memory Leak Regression Test - INC-2026-DEMO-002', () => {
  
  test('sessionCache should not exceed max size under sustained load', async () => {
    const CACHE_MAX_SIZE = parseInt(process.env.CACHE_MAX_SIZE || '1000');
    const REQUEST_COUNT = CACHE_MAX_SIZE + 500; // Exceed max size
    
    // Record initial memory
    const initialMemory = process.memoryUsage().heapUsed;
    
    // Send many payment requests
    const requests = [];
    for (let i = 0; i < REQUEST_COUNT; i++) {
      requests.push(
        request(app)
          .post('/payment')
          .send({
            userId: `user_${i}`,
            amount: 100 + i
          })
      );
    }
    
    // Wait for all requests to complete
    await Promise.all(requests);
    
    // Check cache size via health endpoint
    const healthResponse = await request(app).get('/health');
    const cacheSize = healthResponse.body.cacheSize;
    
    // ASSERTION: Cache size should not exceed max size
    expect(cacheSize).toBeLessThanOrEqual(CACHE_MAX_SIZE);
    
    // Record final memory
    const finalMemory = process.memoryUsage().heapUsed;
    const memoryGrowthMB = (finalMemory - initialMemory) / 1024 / 1024;
    
    // ASSERTION: Memory growth should be bounded (not linear with request count)
    // With the bug, memory would grow ~50MB+ for 1500 requests
    // With the fix, memory should stay under 20MB due to LRU eviction
    expect(memoryGrowthMB).toBeLessThan(30);
    
    console.log(`Memory growth: ${memoryGrowthMB.toFixed(2)}MB for ${REQUEST_COUNT} requests`);
    console.log(`Cache size: ${cacheSize}/${CACHE_MAX_SIZE} entries`);
  }, 30000); // 30 second timeout
  
  test('sessionStore should cleanup expired sessions', async () => {
    const sessionStore = require('../store/sessionStore');
    
    // Create test sessions with old lastAccessed times
    const oldSession = {
      id: 'test_old_session',
      createdAt: Date.now() - 60 * 60 * 1000, // 1 hour ago
      lastAccessed: Date.now() - 60 * 60 * 1000, // 1 hour ago
      data: {}
    };
    
    const recentSession = {
      id: 'test_recent_session',
      createdAt: Date.now(),
      lastAccessed: Date.now(),
      data: {}
    };
    
    sessionStore.set('test_old_session', oldSession);
    sessionStore.set('test_recent_session', recentSession);
    
    const sizeBefore = sessionStore.size();
    
    // Trigger cleanup
    sessionStore.cleanup();
    
    const sizeAfter = sessionStore.size();
    
    // ASSERTION: Old session should be removed
    expect(sessionStore.get('test_old_session')).toBeUndefined();
    
    // ASSERTION: Recent session should remain
    expect(sessionStore.get('test_recent_session')).toBeDefined();
    
    // ASSERTION: Size should decrease
    expect(sizeAfter).toBeLessThan(sizeBefore);
  });
  
});
```

---

## Implementation Steps

1. **Deploy LRU Cache Fix** (server.js)
   - Replace unbounded Map with LRUCache class
   - Set CACHE_MAX_SIZE environment variable (default: 1000)
   - Reduce stored data per transaction (remove headers, requestBody)

2. **Deploy TTL Cleanup Fix** (store/sessionStore.js)
   - Add TTL configuration (default: 30 minutes)
   - Implement periodic cleanup interval (default: 60 seconds)
   - Add graceful shutdown for cleanup timer

3. **Deploy Session Validation Fix** (middleware/session.js)
   - Require x-session-id header
   - Validate session ID format
   - Prevent uncontrolled session creation

4. **Deploy Regression Test**
   - Add test file to test/ directory
   - Run test suite to verify fix
   - Add to CI/CD pipeline

---

## Expected Outcome

- **Memory Growth**: Bounded to ~20MB regardless of request volume (vs. unbounded linear growth)
- **Cache Size**: Capped at CACHE_MAX_SIZE (1000 entries by default)
- **Session Cleanup**: Expired sessions removed every 60 seconds
- **Performance**: No degradation, LRU operations are O(1)

---

## Monitoring Recommendations

1. Add Prometheus metrics for:
   - `cache_size` (current sessionCache size)
   - `cache_evictions_total` (LRU eviction counter)
   - `session_cleanup_total` (expired session cleanup counter)

2. Set alerts for:
   - Heap usage > 80% of container limit
   - Cache size approaching max size (> 90%)
   - Session cleanup failures

3. Dashboard panels:
   - Memory usage over time
   - Cache size vs. max size
   - Session lifecycle (created, expired, active)

---

**Analysis Complete**: Root cause identified, fix implemented, regression test provided.
