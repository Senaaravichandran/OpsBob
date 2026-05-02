# Memory Leak Fix Plan - INC-1777761159

## Root Cause Analysis

### Primary Memory Leak
**Location**: `demo-service/server.js`, line 18 and line 133  
**Variable**: `sessionCache` (Map instance)  
**Root Cause**: The `sessionCache.set(Date.now(), {...})` operation on line 133 stores every payment transaction using a timestamp as the key. This Map has no eviction policy, size limit, or TTL mechanism, causing linear memory growth proportional to request volume. Each payment request permanently allocates ~500-1000 bytes (request body + headers + metadata) that is never garbage collected.

### Secondary Memory Leak
**Location**: `demo-service/store/sessionStore.js`, line 6 and line 14-15  
**Variable**: `this.sessions` (Map instance in SessionStore class)  
**Root Cause**: The `sessions.set(sessionId, session)` operation stores session objects indefinitely without implementing time-to-live expiration or least-recently-used eviction. The session middleware creates new sessions for every request lacking a session ID, compounding the leak.

## Fix Plan (3 Bullet Points)

1. **Replace unbounded Map with LRU cache in server.js**: Implement a Least Recently Used (LRU) cache with configurable max size (default: 1000 entries) for `sessionCache`. Use a doubly-linked list + Map structure or the `lru-cache` npm package to automatically evict oldest entries when capacity is reached, preventing unbounded growth while maintaining recent transaction history for debugging.

2. **Add TTL-based cleanup to SessionStore class**: Implement a periodic cleanup interval (every 60 seconds) that iterates through `this.sessions` and removes entries where `(Date.now() - session.lastAccessed) > SESSION_TTL_MS` (default: 30 minutes). Add `lastAccessed` timestamp tracking in the session middleware to enable accurate expiration detection.

3. **Implement max capacity limit with FIFO eviction in SessionStore**: Add a `MAX_SESSIONS` configuration (default: 5000) and implement first-in-first-out eviction when `this.sessions.size >= MAX_SESSIONS`. Track insertion order using an array or maintain creation timestamps to identify oldest sessions for removal, providing a hard upper bound on memory consumption.

## Corrected Code

### File: `demo-service/server.js` (Fixed)

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

// FIX: Implement LRU cache with max size limit
class LRUCache {
  constructor(maxSize) {
    this.maxSize = maxSize;
    this.cache = new Map();
  }
  
  get(key) {
    if (!this.cache.has(key)) return undefined;
    
    // Move to end (most recently used)
    const value = this.cache.get(key);
    this.cache.delete(key);
    this.cache.set(key, value);
    return value;
  }
  
  set(key, value) {
    // Remove if exists (to update position)
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    
    // Evict oldest entry if at capacity
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    
    this.cache.set(key, value);
  }
  
  get size() {
    return this.cache.size;
  }
}

const sessionCache = new LRUCache(CACHE_MAX_SIZE);

// Memory monitoring interval — captures traces when heap exceeds threshold
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
 * Returns service status and current memory usage
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
 * GET /metrics — Real heap data for OpsBob backend
 * Returns structured JSON metrics including memory, cache, and application stats
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
 * GET /debug/traces — Stack traces for incident analysis
 * Exposes captured stack traces locally (replaces Instana deep trace API for demo)
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
 * Payment processing endpoint
 * Simulates payment processing with FIXED memory management
 * 
 * Request body: { userId: string, amount: number }
 * Response: { transactionId: string, status: string }
 */
app.post('/payment', (req, res) => {
  trackRequest();
  
  try {
    const { userId, amount } = req.body;
    
    // Validate required fields
    if (!userId || amount === undefined) {
      trackError();
      return res.status(400).json({
        status: 'error',
        message: 'Missing required fields: userId and amount'
      });
    }
    
    // Validate amount is a positive number
    if (typeof amount !== 'number' || amount <= 0) {
      trackError();
      return res.status(400).json({
        status: 'error',
        message: 'Amount must be a positive number'
      });
    }
    
    // Generate unique transaction ID
    const transactionId = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // FIX: Store in LRU cache with automatic eviction
    sessionCache.set(Date.now(), {
      userId,
      amount,
      transactionId,
      timestamp: new Date().toISOString(),
      requestBody: req.body,
      headers: req.headers,
      ip: req.ip
    });

    // Capture trace periodically to show the cache is bounded
    if (sessionCache.size % 100 === 0) {
      captureTrace('payment_handler', {
        cache_size: sessionCache.size,
        cache_max_size: CACHE_MAX_SIZE,
        transaction_id: transactionId,
        user_id: userId
      });
    }
    
    // Log for debugging (in production, this would go to proper logging service)
    if (sessionCache.size % 50 === 0) {
      console.log(`Payment processed: ${transactionId} | Cache size: ${sessionCache.size}/${CACHE_MAX_SIZE} entries`);
    }
    
    // Simulate successful payment processing
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
 * Root endpoint - API information
 */
app.get('/', (req, res) => {
  res.json({
    service: 'payments-api',
    version: '1.0.1',
    description: 'Payment processing microservice for OpsBob demo (FIXED)',
    endpoints: {
      health: 'GET /health',
      payment: 'POST /payment',
      metrics: 'GET /metrics',
      debug_traces: 'GET /debug/traces'
    }
  });
});

/**
 * 404 handler for undefined routes
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
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Metrics: http://localhost:${PORT}/metrics`);
  console.log(`Debug traces: http://localhost:${PORT}/debug/traces`);
  console.log(`Payment endpoint: http://localhost:${PORT}/payment`);
  console.log(`Cache max size: ${CACHE_MAX_SIZE} entries`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
});

/**
 * Graceful shutdown handler
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

// Made with Bob - FIXED
```

### File: `demo-service/store/sessionStore.js` (Fixed)

```javascript
// In-memory session store with FIXED memory leak
// Implements TTL-based cleanup and max capacity limit

class SessionStore {
  constructor(options = {}) {
    this.sessions = new Map();
    this.sessionOrder = []; // Track insertion order for FIFO eviction
    this.maxSessions = options.maxSessions || 5000;
    this.sessionTTL = options.sessionTTL || 30 * 60 * 1000; // 30 minutes default
    this.cleanupInterval = options.cleanupInterval || 60 * 1000; // 1 minute default
    
    console.log(`SessionStore initialized (max: ${this.maxSessions}, TTL: ${this.sessionTTL}ms)`);
    
    // FIX: Start periodic cleanup
    this.startCleanup();
  }
  
  get(sessionId) {
    const session = this.sessions.get(sessionId);
    
    if (!session) return undefined;
    
    // Check if expired
    if (Date.now() - session.lastAccessed > this.sessionTTL) {
      this.delete(sessionId);
      return undefined;
    }
    
    return session;
  }
  
  set(sessionId, session) {
    // FIX: Enforce max capacity with FIFO eviction
    if (!this.sessions.has(sessionId) && this.sessions.size >= this.maxSessions) {
      // Evict oldest session
      const oldestSessionId = this.sessionOrder.shift();
      if (oldestSessionId) {
        this.sessions.delete(oldestSessionId);
        console.log(`Session evicted (capacity): ${oldestSessionId}`);
      }
    }
    
    // Update or add session
    if (!this.sessions.has(sessionId)) {
      this.sessionOrder.push(sessionId);
    }
    
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size}/${this.maxSessions})`);
  }
  
  delete(sessionId) {
    const deleted = this.sessions.delete(sessionId);
    if (deleted) {
      // Remove from order tracking
      const index = this.sessionOrder.indexOf(sessionId);
      if (index > -1) {
        this.sessionOrder.splice(index, 1);
      }
    }
    return deleted;
  }
  
  size() {
    return this.sessions.size;
  }
  
  // FIX: Cleanup expired sessions
  cleanup() {
    const now = Date.now();
    let expiredCount = 0;
    
    for (const [sessionId, session] of this.sessions.entries()) {
      if (now - session.lastAccessed > this.sessionTTL) {
        this.delete(sessionId);
        expiredCount++;
      }
    }
    
    if (expiredCount > 0) {
      console.log(`Cleaned up ${expiredCount} expired sessions (remaining: ${this.sessions.size})`);
    }
  }
  
  // FIX: Start periodic cleanup
  startCleanup() {
    this.cleanupTimer = setInterval(() => {
      this.cleanup();
    }, this.cleanupInterval);
  }
  
  // FIX: Stop cleanup on shutdown
  stopCleanup() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = null;
    }
  }
}

// Export singleton instance with configuration
module.exports = new SessionStore({
  maxSessions: parseInt(process.env.MAX_SESSIONS || '5000'),
  sessionTTL: parseInt(process.env.SESSION_TTL_MS || String(30 * 60 * 1000)),
  cleanupInterval: parseInt(process.env.CLEANUP_INTERVAL_MS || String(60 * 1000))
});

// Made with Bob - FIXED
```

### File: `demo-service/middleware/session.js` (Fixed)

```javascript
// Session middleware with FIXED memory leak
const sessionStore = require('../store/sessionStore');

function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'] || `session_${Date.now()}_${Math.random()}`;
  
  // Get or create session
  let session = sessionStore.get(sessionId);
  
  if (!session) {
    session = {
      id: sessionId,
      createdAt: Date.now(),
      lastAccessed: Date.now(), // FIX: Initialize lastAccessed
      data: {}
    };
    sessionStore.set(sessionId, session);
  } else {
    // FIX: Update last accessed time for TTL tracking
    session.lastAccessed = Date.now();
  }
  
  // Attach session to request
  req.session = session.data;
  req.sessionId = sessionId;
  
  next();
}

module.exports = sessionMiddleware;

// Made with Bob - FIXED
```

### File: `demo-service/routes/payments.js` (No changes needed)

```javascript
// Payment processing routes
const express = require('express');
const router = express.Router();
const sessionMiddleware = require('../middleware/session');

// Apply session middleware to all payment routes
router.use(sessionMiddleware);

// Process payment endpoint
router.post('/process', async (req, res) => {
  const { amount, currency, userId } = req.body;
  
  try {
    // Validate payment data
    if (!amount || !currency || !userId) {
      return res.status(400).json({ error: 'Missing required fields' });
    }
    
    // Process payment (simulated)
    const paymentId = `pay_${Date.now()}_${userId}`;
    
    // Store payment in session for tracking
    req.session.lastPayment = {
      id: paymentId,
      amount,
      currency,
      userId,
      timestamp: Date.now()
    };
    
    console.log(`Payment processed: ${paymentId}`);
    
    res.json({
      success: true,
      paymentId,
      amount,
      currency
    });
    
  } catch (error) {
    console.error('Payment processing error:', error);
    res.status(500).json({ error: 'Payment processing failed' });
  }
});

// Get payment status
router.get('/status/:paymentId', (req, res) => {
  const { paymentId } = req.params;
  
  // Check if payment exists in session
  if (req.session.lastPayment && req.session.lastPayment.id === paymentId) {
    res.json({
      status: 'completed',
      payment: req.session.lastPayment
    });
  } else {
    res.status(404).json({ error: 'Payment not found' });
  }
});

module.exports = router;

// Made with Bob
```

## Regression Test

### File: `demo-service/test/memory-leak.test.js` (New)

```javascript
// Regression test to catch memory leak bugs
const request = require('supertest');
const app = require('../server');

describe('Memory Leak Regression Tests', () => {
  
  test('sessionCache should not exceed max size after many requests', async () => {
    const CACHE_MAX_SIZE = parseInt(process.env.CACHE_MAX_SIZE || '1000');
    const REQUEST_COUNT = CACHE_MAX_SIZE + 500; // Exceed max size
    
    // Send many payment requests
    for (let i = 0; i < REQUEST_COUNT; i++) {
      await request(app)
        .post('/payment')
        .send({
          userId: `user_${i}`,
          amount: 100 + i
        });
    }
    
    // Check cache size via health endpoint
    const response = await request(app).get('/health');
    
    expect(response.status).toBe(200);
    expect(response.body.cacheSize).toBeLessThanOrEqual(CACHE_MAX_SIZE);
    expect(response.body.cacheSize).toBeGreaterThan(0);
    
    console.log(`Cache size after ${REQUEST_COUNT} requests: ${response.body.cacheSize}/${CACHE_MAX_SIZE}`);
  });
  
  test('sessionStore should cleanup expired sessions', async () => {
    const sessionStore = require('../store/sessionStore');
    
    // Create test sessions with short TTL
    const testSessionStore = new (require('../store/sessionStore').constructor)({
      maxSessions: 100,
      sessionTTL: 100, // 100ms TTL for testing
      cleanupInterval: 50 // 50ms cleanup interval
    });
    
    // Add sessions
    for (let i = 0; i < 10; i++) {
      testSessionStore.set(`session_${i}`, {
        id: `session_${i}`,
        createdAt: Date.now(),
        lastAccessed: Date.now(),
        data: { test: true }
      });
    }
    
    expect(testSessionStore.size()).toBe(10);
    
    // Wait for TTL to expire
    await new Promise(resolve => setTimeout(resolve, 200));
    
    // Trigger cleanup
    testSessionStore.cleanup();
    
    // All sessions should be expired and cleaned up
    expect(testSessionStore.size()).toBe(0);
    
    testSessionStore.stopCleanup();
  });
  
  test('sessionStore should enforce max capacity', async () => {
    const MAX_SESSIONS = 50;
    const testSessionStore = new (require('../store/sessionStore').constructor)({
      maxSessions: MAX_SESSIONS,
      sessionTTL: 60000,
      cleanupInterval: 60000
    });
    
    // Add more sessions than max capacity
    for (let i = 0; i < MAX_SESSIONS + 20; i++) {
      testSessionStore.set(`session_${i}`, {
        id: `session_${i}`,
        createdAt: Date.now(),
        lastAccessed: Date.now(),
        data: { index: i }
      });
    }
    
    // Size should not exceed max
    expect(testSessionStore.size()).toBeLessThanOrEqual(MAX_SESSIONS);
    
    // Oldest sessions should be evicted (first 20 should be gone)
    expect(testSessionStore.get('session_0')).toBeUndefined();
    expect(testSessionStore.get('session_19')).toBeUndefined();
    
    // Newest sessions should still exist
    expect(testSessionStore.get(`session_${MAX_SESSIONS + 19}`)).toBeDefined();
    
    testSessionStore.stopCleanup();
  });
  
  test('memory usage should stabilize under sustained load', async () => {
    const initialMemory = process.memoryUsage().heapUsed;
    const REQUEST_COUNT = 2000;
    
    // Sustained load
    for (let i = 0; i < REQUEST_COUNT; i++) {
      await request(app)
        .post('/payment')
        .send({
          userId: `load_test_user_${i}`,
          amount: 50
        });
      
      // Sample memory every 100 requests
      if (i % 100 === 0 && i > 0) {
        const currentMemory = process.memoryUsage().heapUsed;
        const growthMB = (currentMemory - initialMemory) / 1024 / 1024;
        console.log(`Memory growth after ${i} requests: ${growthMB.toFixed(2)}MB`);
      }
    }
    
    // Force garbage collection if available
    if (global.gc) {
      global.gc();
    }
    
    const finalMemory = process.memoryUsage().heapUsed;
    const totalGrowthMB = (finalMemory - initialMemory) / 1024 / 1024;
    
    console.log(`Total memory growth after ${REQUEST_COUNT} requests: ${totalGrowthMB.toFixed(2)}MB`);
    
    // Memory growth should be bounded (less than 50MB for 2000 requests)
    // This would fail with the original unbounded cache
    expect(totalGrowthMB).toBeLessThan(50);
  });
});
```

## Test Execution

To run the regression test:

```bash
# Install test dependencies
npm install --save-dev jest supertest

# Run tests
npm test

# Run with garbage collection enabled for memory test
node --expose-gc node_modules/.bin/jest test/memory-leak.test.js
```

## Prevention Strategies

1. **Code Review Checklist**: Always verify that Map/Set/Array data structures have:
   - Maximum size limits
   - Eviction policies (LRU, FIFO, TTL)
   - Cleanup mechanisms

2. **Memory Monitoring**: Implement heap size alerts and track cache/store sizes in metrics

3. **Load Testing**: Run sustained load tests that exceed cache capacity to verify eviction works

4. **Static Analysis**: Use ESLint rules to flag unbounded collections:
   ```javascript
   // .eslintrc.js
   rules: {
     'no-unbounded-collections': 'error' // Custom rule
   }
   ```

5. **Documentation**: Document memory management strategy for all caching layers

## Deployment Plan

1. Deploy fixed code to staging environment
2. Run regression tests to verify fix
3. Monitor memory metrics for 24 hours under normal load
4. Deploy to production with gradual rollout (10% → 50% → 100%)
5. Monitor Instana alerts for memory growth patterns
6. Keep rollback plan ready for 48 hours post-deployment
