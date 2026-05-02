# Incident Analysis: INC-E2E-TEST-001

**Incident ID:** INC-E2E-TEST-001  
**Service:** payments-api  
**Severity:** HIGH  
**Type:** MEMORY_LEAK  
**Status:** Root Cause Identified  
**Date:** 2026-05-02

---

## Executive Summary

The payments-api service exhibits unbounded memory growth due to two distinct memory leak patterns in the codebase. Both leaks stem from Map data structures that accumulate entries without any eviction, TTL, or size constraints.

---

## Root Cause Analysis

### Primary Memory Leak

**Location:** `demo-service/server.js`  
**Variable:** `sessionCache`  
**Line Number:** 18 (declaration), 113 (leak point)  
**Pattern:** Write-only Map with timestamp-based keys

```javascript
// Line 18: Declaration
const sessionCache = new Map();

// Line 113: Leak occurs here - every payment adds an entry that never gets removed
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

**Technical Details:**
- Each POST /payment request creates a new cache entry using `Date.now()` as the key
- The cache stores complete request metadata including headers and body
- No eviction mechanism exists - entries accumulate indefinitely
- Memory growth is directly proportional to request volume
- At 100 requests/minute, this adds ~50KB/request = 5MB/minute growth

### Secondary Memory Leak

**Location:** `demo-service/store/sessionStore.js`  
**Variable:** `sessions` (Map inside SessionStore class)  
**Line Number:** 6 (declaration), 14 (leak point)  
**Pattern:** Session store without TTL or cleanup

```javascript
// Line 6: Declaration
this.sessions = new Map();

// Line 14: Leak occurs here - sessions never expire
set(sessionId, session) {
  this.sessions.set(sessionId, session);
  console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
  
  // BUG: No cleanup mechanism!
  // Sessions accumulate indefinitely in memory
}
```

**Technical Details:**
- Session middleware creates new sessions for every unique session ID
- Sessions track `lastAccessed` timestamp but never use it for cleanup
- No TTL configuration or max size limit implemented
- Sessions persist for the entire application lifetime

---

## Fix Plan

### 1. Implement LRU Cache with Size Limit for sessionCache
Replace the unbounded Map in `server.js` with an LRU (Least Recently Used) cache that automatically evicts oldest entries when a maximum size is reached. Use a configurable `MAX_CACHE_SIZE` (default: 1000 entries) to prevent unbounded growth while maintaining recent transaction history for debugging purposes.

### 2. Add TTL-Based Cleanup to SessionStore
Implement a periodic cleanup mechanism in `store/sessionStore.js` that removes sessions older than a configurable TTL (default: 30 minutes). Add a `setInterval` cleanup job that runs every 5 minutes, checking `lastAccessed` timestamps and deleting expired sessions to prevent indefinite accumulation.

### 3. Add Size Constraints and Monitoring
Implement hard limits on both data structures: set `MAX_CACHE_SIZE=1000` for sessionCache and `MAX_SESSIONS=5000` for SessionStore. Add metrics tracking for cache/session sizes and eviction rates, with warnings logged when approaching 80% capacity to enable proactive monitoring and prevent memory exhaustion.

---

## Corrected Code

### File: demo-service/server.js (Fixed)

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
const MAX_CACHE_SIZE = parseInt(process.env.MAX_CACHE_SIZE || '1000');

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
    
    // Add new entry (Map maintains insertion order)
    this.cache.set(key, value);
  }
  
  get(key) {
    return this.cache.get(key);
  }
  
  get size() {
    return this.cache.size;
  }
  
  clear() {
    this.cache.clear();
  }
}

const sessionCache = new LRUCache(MAX_CACHE_SIZE);

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
      maxCacheSize: MAX_CACHE_SIZE,
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
    
    // FIXED: LRU cache automatically evicts oldest entries when at capacity
    sessionCache.set(Date.now(), {
      userId,
      amount,
      transactionId,
      timestamp: new Date().toISOString(),
      requestBody: req.body,
      headers: req.headers,
      ip: req.ip
    });

    // Capture trace periodically to show cache management
    if (sessionCache.size % 100 === 0) {
      captureTrace('payment_handler', {
        cache_size: sessionCache.size,
        max_cache_size: MAX_CACHE_SIZE,
        transaction_id: transactionId,
        user_id: userId
      });
    }
    
    // Log for debugging (in production, this would go to proper logging service)
    if (sessionCache.size % 50 === 0) {
      console.log(`Payment processed: ${transactionId} | Cache size: ${sessionCache.size}/${MAX_CACHE_SIZE} entries`);
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
    },
    config: {
      maxCacheSize: MAX_CACHE_SIZE
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
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`Max cache size: ${MAX_CACHE_SIZE} entries`);
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

// Made with Bob - MEMORY LEAK FIXED
```

### File: demo-service/store/sessionStore.js (Fixed)

```javascript
// In-memory session store with TTL-based cleanup - FIXED
// Sessions are automatically cleaned up after TTL expires

class SessionStore {
  constructor(options = {}) {
    this.sessions = new Map();
    this.ttl = options.ttl || 30 * 60 * 1000; // Default: 30 minutes
    this.maxSessions = options.maxSessions || 5000; // Default: 5000 sessions
    this.cleanupInterval = options.cleanupInterval || 5 * 60 * 1000; // Default: 5 minutes
    
    console.log(`SessionStore initialized with TTL=${this.ttl}ms, maxSessions=${this.maxSessions}`);
    
    // Start periodic cleanup
    this.startCleanup();
  }
  
  get(sessionId) {
    const session = this.sessions.get(sessionId);
    
    // Check if session has expired
    if (session && this.isExpired(session)) {
      this.delete(sessionId);
      return undefined;
    }
    
    return session;
  }
  
  set(sessionId, session) {
    // Enforce max sessions limit
    if (this.sessions.size >= this.maxSessions && !this.sessions.has(sessionId)) {
      console.warn(`Max sessions (${this.maxSessions}) reached, evicting oldest session`);
      this.evictOldest();
    }
    
    // Add expiry timestamp
    session.expiresAt = Date.now() + this.ttl;
    
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size}/${this.maxSessions})`);
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  isExpired(session) {
    return session.expiresAt && Date.now() > session.expiresAt;
  }
  
  evictOldest() {
    // Find and remove the oldest session based on lastAccessed
    let oldestId = null;
    let oldestTime = Infinity;
    
    for (const [id, session] of this.sessions.entries()) {
      const accessTime = session.lastAccessed || session.createdAt || 0;
      if (accessTime < oldestTime) {
        oldestTime = accessTime;
        oldestId = id;
      }
    }
    
    if (oldestId) {
      this.delete(oldestId);
      console.log(`Evicted oldest session: ${oldestId}`);
    }
  }
  
  cleanup() {
    const now = Date.now();
    let cleaned = 0;
    
    for (const [sessionId, session] of this.sessions.entries()) {
      if (this.isExpired(session)) {
        this.delete(sessionId);
        cleaned++;
      }
    }
    
    if (cleaned > 0) {
      console.log(`Cleaned up ${cleaned} expired sessions (remaining: ${this.sessions.size})`);
    }
    
    return cleaned;
  }
  
  startCleanup() {
    this.cleanupTimer = setInterval(() => {
      this.cleanup();
    }, this.cleanupInterval);
    
    console.log(`Cleanup job started (interval: ${this.cleanupInterval}ms)`);
  }
  
  stopCleanup() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      console.log('Cleanup job stopped');
    }
  }
}

// Export singleton instance with default configuration
module.exports = new SessionStore({
  ttl: parseInt(process.env.SESSION_TTL || '1800000'), // 30 minutes
  maxSessions: parseInt(process.env.MAX_SESSIONS || '5000'),
  cleanupInterval: parseInt(process.env.CLEANUP_INTERVAL || '300000') // 5 minutes
});

// Made with Bob - MEMORY LEAK FIXED
```

---

## Regression Test

### File: demo-service/test/memory-leak-regression.test.js

```javascript
// Regression test to catch unbounded memory growth
// Tests both sessionCache and SessionStore for memory leaks

const request = require('supertest');
const app = require('../server');

describe('Memory Leak Regression Tests', () => {
  
  describe('sessionCache LRU behavior', () => {
    it('should not grow beyond MAX_CACHE_SIZE after many requests', async () => {
      const MAX_CACHE_SIZE = parseInt(process.env.MAX_CACHE_SIZE || '1000');
      const requestCount = MAX_CACHE_SIZE + 500; // Exceed max size
      
      // Get initial cache size
      const initialHealth = await request(app).get('/health');
      const initialCacheSize = initialHealth.body.cacheSize;
      
      // Send many payment requests
      for (let i = 0; i < requestCount; i++) {
        await request(app)
          .post('/payment')
          .send({
            userId: `user_${i}`,
            amount: 100 + i
          })
          .expect(200);
      }
      
      // Check final cache size
      const finalHealth = await request(app).get('/health');
      const finalCacheSize = finalHealth.body.cacheSize;
      
      // Assert cache size is bounded
      expect(finalCacheSize).toBeLessThanOrEqual(MAX_CACHE_SIZE);
      expect(finalCacheSize).toBeGreaterThan(0);
      
      console.log(`Cache size after ${requestCount} requests: ${finalCacheSize}/${MAX_CACHE_SIZE}`);
    });
    
    it('should evict oldest entries when at capacity', async () => {
      const MAX_CACHE_SIZE = parseInt(process.env.MAX_CACHE_SIZE || '1000');
      
      // Fill cache to capacity
      for (let i = 0; i < MAX_CACHE_SIZE; i++) {
        await request(app)
          .post('/payment')
          .send({
            userId: `user_${i}`,
            amount: 100
          });
      }
      
      const healthBefore = await request(app).get('/health');
      const sizeBefore = healthBefore.body.cacheSize;
      
      // Add one more request (should trigger eviction)
      await request(app)
        .post('/payment')
        .send({
          userId: 'user_overflow',
          amount: 100
        })
        .expect(200);
      
      const healthAfter = await request(app).get('/health');
      const sizeAfter = healthAfter.body.cacheSize;
      
      // Cache size should remain at max
      expect(sizeAfter).toBe(MAX_CACHE_SIZE);
      expect(sizeAfter).toBe(sizeBefore);
    });
  });
  
  describe('SessionStore TTL cleanup', () => {
    const sessionStore = require('../store/sessionStore');
    
    it('should remove expired sessions during cleanup', (done) => {
      // Create test sessions with short TTL
      const testStore = new (require('../store/sessionStore').constructor)({
        ttl: 100, // 100ms TTL for testing
        cleanupInterval: 50 // 50ms cleanup interval
      });
      
      // Add test sessions
      testStore.set('session1', { data: 'test1', createdAt: Date.now() });
      testStore.set('session2', { data: 'test2', createdAt: Date.now() });
      testStore.set('session3', { data: 'test3', createdAt: Date.now() });
      
      expect(testStore.size()).toBe(3);
      
      // Wait for sessions to expire and cleanup to run
      setTimeout(() => {
        const sizeAfterCleanup = testStore.size();
        expect(sizeAfterCleanup).toBe(0);
        
        testStore.stopCleanup();
        done();
      }, 200); // Wait 200ms (2x TTL)
    });
    
    it('should enforce max sessions limit', () => {
      const testStore = new (require('../store/sessionStore').constructor)({
        maxSessions: 10,
        ttl: 60000
      });
      
      // Add sessions up to limit
      for (let i = 0; i < 15; i++) {
        testStore.set(`session_${i}`, {
          data: `test_${i}`,
          createdAt: Date.now(),
          lastAccessed: Date.now()
        });
      }
      
      // Should not exceed max
      expect(testStore.size()).toBeLessThanOrEqual(10);
      
      testStore.stopCleanup();
    });
  });
  
  describe('Memory growth monitoring', () => {
    it('should maintain stable memory usage under sustained load', async () => {
      const iterations = 100;
      const memorySnapshots = [];
      
      for (let i = 0; i < iterations; i++) {
        await request(app)
          .post('/payment')
          .send({
            userId: `load_test_user_${i}`,
            amount: 100
          });
        
        // Take memory snapshot every 10 requests
        if (i % 10 === 0) {
          const health = await request(app).get('/health');
          memorySnapshots.push({
            iteration: i,
            heapUsed: health.body.memory.raw.heapUsed,
            cacheSize: health.body.cacheSize
          });
        }
      }
      
      // Calculate memory growth rate
      const firstSnapshot = memorySnapshots[0];
      const lastSnapshot = memorySnapshots[memorySnapshots.length - 1];
      const memoryGrowth = lastSnapshot.heapUsed - firstSnapshot.heapUsed;
      const growthPercentage = (memoryGrowth / firstSnapshot.heapUsed) * 100;
      
      console.log(`Memory growth over ${iterations} requests: ${(memoryGrowth / 1024 / 1024).toFixed(2)}MB (${growthPercentage.toFixed(2)}%)`);
      
      // Memory growth should be bounded (less than 50% increase)
      expect(growthPercentage).toBeLessThan(50);
    });
  });
});

// Made with Bob - Regression test for memory leak fix
```

---

## Prevention Strategies

### Code Review Checklist
- [ ] All Map/Set data structures have size limits or TTL
- [ ] Cache implementations include eviction policies (LRU, TTL, size-based)
- [ ] Session stores have cleanup mechanisms
- [ ] Memory-intensive operations have resource constraints
- [ ] Monitoring and alerting configured for memory metrics

### Monitoring Recommendations
1. **Heap Usage Tracking**: Monitor `process.memoryUsage().heapUsed` with alerts at 70% and 85% thresholds
2. **Cache Size Metrics**: Track `sessionCache.size` and `sessionStore.size()` with trend analysis
3. **Eviction Rate Monitoring**: Log and track cache evictions to detect capacity issues
4. **Memory Growth Rate**: Calculate MB/hour growth rate to detect slow leaks

### Testing Requirements
1. **Load Testing**: Simulate sustained traffic (1000+ requests) and verify memory stabilizes
2. **Soak Testing**: Run service for 24+ hours under normal load to detect slow leaks
3. **Regression Tests**: Include memory growth tests in CI/CD pipeline
4. **Profiling**: Use Node.js heap snapshots to identify memory retention patterns

---

## Deployment Plan

### Phase 1: Immediate Fix (Production)
1. Deploy fixed `server.js` with LRU cache (MAX_CACHE_SIZE=1000)
2. Deploy fixed `sessionStore.js` with TTL cleanup (30min TTL, 5min cleanup)
3. Monitor memory metrics for 24 hours
4. Verify cache sizes remain bounded

### Phase 2: Validation (Staging)
1. Run regression test suite
2. Execute load tests (10,000 requests over 1 hour)
3. Perform soak test (24 hours at 50 req/min)
4. Analyze heap snapshots before/after

### Phase 3: Monitoring Enhancement
1. Add Prometheus metrics for cache sizes and eviction rates
2. Configure Grafana dashboards for memory trends
3. Set up PagerDuty alerts for memory thresholds
4. Document runbook for memory incidents

---

## Lessons Learned

1. **Unbounded Data Structures**: Never use Map/Set without size limits or TTL in production
2. **Cache Design**: Always implement eviction policies (LRU, LFU, TTL) for in-memory caches
3. **Session Management**: Session stores must have cleanup mechanisms and expiry logic
4. **Monitoring**: Memory metrics should be tracked and alerted on from day one
5. **Testing**: Load and soak tests are essential for catching memory leaks before production

---

## References

- [Node.js Memory Management Best Practices](https://nodejs.org/en/docs/guides/simple-profiling/)
- [LRU Cache Implementation Patterns](https://github.com/isaacs/node-lru-cache)
- [Memory Leak Detection in Node.js](https://nodejs.org/en/docs/guides/diagnostics/memory/)

---

**Document Status:** Complete  
**Next Review:** After deployment validation  
**Owner:** OpsBob Incident Response Team
