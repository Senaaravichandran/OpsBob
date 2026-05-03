# Memory Leak Fix Implementation Plan

## Overview
This document provides the detailed implementation plan for fixing the memory leaks identified in INC-TEST-001.

---

## Fix 1: TTL-Based Eviction for sessionCache (server.js)

### Current Code (Lines 18, 109-120)
```javascript
const sessionCache = new Map();

// Inside /payment endpoint:
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

### Proposed Changes

**1. Add configuration constant (after line 13)**
```javascript
const SESSION_TTL_MS = parseInt(process.env.SESSION_TTL_MS || '300000'); // 5 minutes default
```

**2. Modify sessionCache structure (line 18)**
```javascript
const sessionCache = new Map(); // Keep as-is, but store wrapped objects
```

**3. Add cleanup scheduler (after sessionCache declaration, ~line 19)**
```javascript
// Cleanup expired sessions every 60 seconds
const sessionCleanup = setInterval(() => {
  const now = Date.now();
  let cleaned = 0;
  
  for (const [key, value] of sessionCache.entries()) {
    if (now - value.createdAt > SESSION_TTL_MS) {
      sessionCache.delete(key);
      cleaned++;
    }
  }
  
  if (cleaned > 0) {
    console.log(`🧹 Cleaned ${cleaned} expired sessions from cache (remaining: ${sessionCache.size})`);
  }
}, 60000);
```

**4. Update sessionCache.set() call (line 109)**
```javascript
sessionCache.set(Date.now(), {
  createdAt: Date.now(), // ADD THIS LINE
  userId,
  amount,
  transactionId,
  timestamp: new Date().toISOString(),
  requestBody: req.body,
  headers: req.headers,
  ip: req.ip
});
```

**5. Update shutdown handlers (add cleanup to SIGTERM/SIGINT)**
```javascript
process.on('SIGTERM', () => {
  console.log('SIGTERM signal received: closing HTTP server');
  clearInterval(memoryMonitor);
  clearInterval(sessionCleanup); // ADD THIS LINE
  server.close(() => {
    console.log('HTTP server closed');
    process.exit(0);
  });
});
```

---

## Fix 2: LRU Cache for SessionStore (store/sessionStore.js)

### Option A: Using lru-cache npm package (Recommended)

**1. Install dependency**
```bash
npm install lru-cache@10
```

**2. Replace entire SessionStore class**
```javascript
const { LRUCache } = require('lru-cache');

class SessionStore {
  constructor() {
    this.sessions = new LRUCache({
      max: 10000, // Maximum 10k sessions
      ttl: 1800000, // 30 minutes TTL
      updateAgeOnGet: true, // Refresh TTL on access
      dispose: (value, key) => {
        console.log(`Session expired: ${key}`);
      }
    });
    console.log('SessionStore initialized with LRU cache (max: 10000, ttl: 30min)');
  }
  
  get(sessionId) {
    return this.sessions.get(sessionId);
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
}

module.exports = new SessionStore();
```

### Option B: Manual LRU Implementation (No dependencies)

**Replace entire SessionStore class**
```javascript
class SessionStore {
  constructor() {
    this.sessions = new Map();
    this.maxSize = 10000;
    this.ttl = 1800000; // 30 minutes
    console.log('SessionStore initialized with manual LRU');
    
    // Cleanup expired sessions every 60 seconds
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60000);
  }
  
  get(sessionId) {
    const entry = this.sessions.get(sessionId);
    if (!entry) return undefined;
    
    // Check if expired
    if (Date.now() - entry.lastAccessed > this.ttl) {
      this.sessions.delete(sessionId);
      return undefined;
    }
    
    // Update access time (LRU)
    entry.lastAccessed = Date.now();
    return entry.data;
  }
  
  set(sessionId, session) {
    // Enforce max size (evict oldest if needed)
    if (this.sessions.size >= this.maxSize && !this.sessions.has(sessionId)) {
      const oldestKey = this.sessions.keys().next().value;
      this.sessions.delete(oldestKey);
      console.log(`Evicted oldest session: ${oldestKey}`);
    }
    
    this.sessions.set(sessionId, {
      data: session,
      lastAccessed: Date.now()
    });
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  cleanup() {
    const now = Date.now();
    let cleaned = 0;
    
    for (const [key, entry] of this.sessions.entries()) {
      if (now - entry.lastAccessed > this.ttl) {
        this.sessions.delete(key);
        cleaned++;
      }
    }
    
    if (cleaned > 0) {
      console.log(`🧹 Cleaned ${cleaned} expired sessions (remaining: ${this.sessions.size})`);
    }
  }
  
  destroy() {
    clearInterval(this.cleanupInterval);
  }
}

module.exports = new SessionStore();
```

---

## Fix 3: Session Middleware Cleanup (middleware/session.js)

### Current Code
```javascript
function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'] || `session_${Date.now()}_${Math.random()}`;
  
  let session = sessionStore.get(sessionId);
  
  if (!session) {
    session = {
      id: sessionId,
      createdAt: Date.now(),
      data: {}
    };
    sessionStore.set(sessionId, session);
  }
  
  req.session = session.data;
  req.sessionId = sessionId;
  
  session.lastAccessed = Date.now();
  
  next();
}
```

### Proposed Changes

**Update to work with new SessionStore structure**
```javascript
function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'] || `session_${Date.now()}_${Math.random()}`;
  
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
  
  // Update last accessed time (handled by SessionStore.get() in new implementation)
  // No need to manually update lastAccessed here anymore
  
  next();
}

module.exports = sessionMiddleware;
```

---

## Regression Test Implementation

### Test File: `demo-service/test/memory-leak.test.js`

```javascript
const request = require('supertest');
const app = require('../server');

describe('Memory Leak Prevention', () => {
  jest.setTimeout(400000); // 400 seconds for cleanup cycles
  
  test('sessionCache should not grow unbounded', async () => {
    // Get baseline memory
    const baselineRes = await request(app).get('/health');
    const baselineHeap = baselineRes.body.memory.raw.heapUsed;
    const baselineCacheSize = baselineRes.body.cacheSize;
    
    console.log(`Baseline: heap=${Math.round(baselineHeap/1024/1024)}MB, cache=${baselineCacheSize}`);
    
    // Generate load: 1000 payment requests
    console.log('Generating load: 1000 payment requests...');
    const promises = [];
    for (let i = 0; i < 1000; i++) {
      promises.push(
        request(app)
          .post('/payment')
          .send({
            userId: `user_${i}`,
            amount: Math.random() * 1000
          })
      );
    }
    await Promise.all(promises);
    
    // Check cache grew
    const afterLoadRes = await request(app).get('/health');
    const afterLoadCacheSize = afterLoadRes.body.cacheSize;
    console.log(`After load: cache=${afterLoadCacheSize}`);
    expect(afterLoadCacheSize).toBeGreaterThan(baselineCacheSize);
    
    // Wait for cleanup cycles (6 minutes for 5min TTL + buffer)
    console.log('Waiting 6 minutes for cleanup cycles...');
    await new Promise(resolve => setTimeout(resolve, 360000));
    
    // Verify cleanup occurred
    const afterCleanupRes = await request(app).get('/health');
    const afterCleanupHeap = afterCleanupRes.body.memory.raw.heapUsed;
    const afterCleanupCacheSize = afterCleanupRes.body.cacheSize;
    
    const heapGrowthMB = (afterCleanupHeap - baselineHeap) / 1024 / 1024;
    
    console.log(`After cleanup: heap=${Math.round(afterCleanupHeap/1024/1024)}MB, cache=${afterCleanupCacheSize}`);
    console.log(`Heap growth: ${heapGrowthMB.toFixed(2)}MB`);
    
    // Assertions
    expect(heapGrowthMB).toBeLessThan(10); // Memory growth < 10MB
    expect(afterCleanupCacheSize).toBeLessThan(100); // Most entries evicted
  });
  
  test('SessionStore should enforce size limits', async () => {
    // This test would require exposing sessionStore size via /health
    // or creating a dedicated test endpoint
    
    // Generate 15,000 unique sessions (exceeds 10k limit)
    const promises = [];
    for (let i = 0; i < 15000; i++) {
      promises.push(
        request(app)
          .post('/payment')
          .set('x-session-id', `test_session_${i}`)
          .send({
            userId: `user_${i}`,
            amount: 100
          })
      );
    }
    await Promise.all(promises);
    
    // Verify store size is capped
    const healthRes = await request(app).get('/health');
    // Would need to add sessionStoreSize to /health response
    // expect(healthRes.body.sessionStoreSize).toBeLessThanOrEqual(10000);
  });
});
```

### Test Dependencies
Add to `demo-service/package.json`:
```json
{
  "devDependencies": {
    "jest": "^29.7.0",
    "supertest": "^6.3.3"
  },
  "scripts": {
    "test": "jest",
    "test:memory": "jest test/memory-leak.test.js"
  }
}
```

---

## Implementation Order

1. ✅ **Fix 1**: sessionCache TTL eviction (server.js) - **PRIORITY 1**
2. ✅ **Fix 2**: SessionStore LRU cache (store/sessionStore.js) - **PRIORITY 2**
3. ✅ **Fix 3**: Middleware cleanup (middleware/session.js) - **PRIORITY 3**
4. ✅ **Test**: Regression test (test/memory-leak.test.js) - **PRIORITY 4**

---

## Validation Checklist

- [ ] sessionCache cleanup interval runs every 60s
- [ ] Expired sessions are removed after TTL
- [ ] SessionStore enforces 10k max size
- [ ] SessionStore TTL is 30 minutes
- [ ] Memory growth stabilizes under sustained load
- [ ] Regression test passes
- [ ] No functional regressions in payment processing
- [ ] Logs show cleanup activity

---

## Rollback Plan

If issues arise post-deployment:
1. Revert to previous version via git
2. Increase TTL values if legitimate sessions are being evicted too aggressively
3. Increase max size if 10k limit is too restrictive for production load

---

## Monitoring Post-Deployment

**Metrics to watch**:
- Heap memory usage trend (should stabilize)
- sessionCache.size (should oscillate, not grow linearly)
- SessionStore size (should stay under 10k)
- Cleanup log frequency (should see regular cleanup activity)
- Payment processing latency (should not increase)

**Alert thresholds**:
- Heap > 500MB for > 10 minutes
- sessionCache.size > 5000
- SessionStore size > 9500
