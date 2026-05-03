# Memory Leak Fix Implementation Plan
## Incident: INC-DEMO-SER-1777806955273

## Overview
This document provides the complete implementation plan to fix the memory leak in demo-service3, including corrected code and regression tests.

---

## Fix 1: Bounded LRU Cache for sessionCache (server.js)

### Current Code (Lines 15, 95-104)
```javascript
// BUG: Unbounded cache
const sessionCache = new Map();

// In /payment endpoint:
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

### Fixed Code
```javascript
// Add at top of file after requires
const LRU = require('lru-cache');

// Replace line 15 with bounded LRU cache
const sessionCache = new LRU({
  max: 1000,              // Maximum 1000 entries
  ttl: 1000 * 60 * 5,     // 5 minute TTL
  updateAgeOnGet: false,   // Don't refresh TTL on read
  dispose: (value, key) => {
    // Optional: Log evictions for monitoring
    if (process.env.NODE_ENV === 'development') {
      console.log(`Cache evicted: ${key}`);
    }
  }
});

// In /payment endpoint (lines 95-104) - NO CHANGES NEEDED
// LRU cache automatically evicts oldest entries when max size reached
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

### Package Dependency
```json
// Add to package.json dependencies
"lru-cache": "^10.0.0"
```

### Installation Command
```bash
cd demo-service3
npm install lru-cache@^10.0.0
```

---

## Fix 2: TTL-Based Cleanup for SessionStore (store/sessionStore.js)

### Current Code (Entire File)
```javascript
class SessionStore {
  constructor() {
    this.sessions = new Map();
    console.log('SessionStore initialized');
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

### Fixed Code (Complete Replacement)
```javascript
// In-memory session store with TTL-based cleanup and size limits
class SessionStore {
  constructor(options = {}) {
    this.sessions = new Map();
    this.maxSize = options.maxSize || 10000;           // Max 10k sessions
    this.sessionTTL = options.sessionTTL || 1800000;   // 30 minutes default
    this.cleanupInterval = options.cleanupInterval || 60000; // 1 minute
    
    // Start periodic cleanup
    this.cleanupTimer = setInterval(() => this.cleanup(), this.cleanupInterval);
    
    console.log(`SessionStore initialized (maxSize: ${this.maxSize}, TTL: ${this.sessionTTL}ms)`);
  }
  
  get(sessionId) {
    const session = this.sessions.get(sessionId);
    
    // Check if session expired
    if (session && this.isExpired(session)) {
      this.delete(sessionId);
      return undefined;
    }
    
    return session;
  }
  
  set(sessionId, session) {
    // Enforce max size limit with LRU eviction
    if (this.sessions.size >= this.maxSize && !this.sessions.has(sessionId)) {
      this.evictOldest();
    }
    
    // Add expiration timestamp
    session.expiresAt = Date.now() + this.sessionTTL;
    
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  // Check if session has expired
  isExpired(session) {
    return Date.now() > session.expiresAt;
  }
  
  // Remove expired sessions
  cleanup() {
    const before = this.sessions.size;
    let removed = 0;
    
    for (const [sessionId, session] of this.sessions.entries()) {
      if (this.isExpired(session)) {
        this.sessions.delete(sessionId);
        removed++;
      }
    }
    
    if (removed > 0) {
      console.log(`SessionStore cleanup: removed ${removed} expired sessions (${before} -> ${this.sessions.size})`);
    }
  }
  
  // Evict oldest session when max size reached
  evictOldest() {
    // Find session with oldest lastAccessed time
    let oldestId = null;
    let oldestTime = Infinity;
    
    for (const [sessionId, session] of this.sessions.entries()) {
      if (session.lastAccessed < oldestTime) {
        oldestTime = session.lastAccessed;
        oldestId = sessionId;
      }
    }
    
    if (oldestId) {
      this.sessions.delete(oldestId);
      console.log(`SessionStore: evicted oldest session ${oldestId}`);
    }
  }
  
  // Graceful shutdown
  destroy() {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer);
      this.cleanupTimer = null;
    }
    this.sessions.clear();
    console.log('SessionStore destroyed');
  }
}

// Export singleton instance with configurable options
const store = new SessionStore({
  maxSize: parseInt(process.env.SESSION_MAX_SIZE || '10000'),
  sessionTTL: parseInt(process.env.SESSION_TTL_MS || '1800000'),
  cleanupInterval: parseInt(process.env.SESSION_CLEANUP_INTERVAL_MS || '60000')
});

// Cleanup on process termination
process.on('SIGTERM', () => store.destroy());
process.on('SIGINT', () => store.destroy());

module.exports = store;

// Made with Bob
```

---

## Fix 3: Session Expiration in Middleware (middleware/session.js)

### Current Code (Entire File)
```javascript
const sessionStore = require('../store/sessionStore');

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

module.exports = sessionMiddleware;
```

### Fixed Code (Complete Replacement)
```javascript
// Session middleware with expiration handling
const sessionStore = require('../store/sessionStore');

function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'] || `session_${Date.now()}_${Math.random()}`;
  
  // Try to get existing session
  let session = sessionStore.get(sessionId);
  
  // Create new session if not found or expired
  if (!session) {
    session = {
      id: sessionId,
      createdAt: Date.now(),
      lastAccessed: Date.now(),
      data: {}
    };
    sessionStore.set(sessionId, session);
  } else {
    // Update last accessed time for existing session
    session.lastAccessed = Date.now();
    // Re-save to update expiration timestamp
    sessionStore.set(sessionId, session);
  }
  
  // Attach session to request
  req.session = session.data;
  req.sessionId = sessionId;
  
  // Set session ID in response header for client tracking
  res.setHeader('X-Session-ID', sessionId);
  
  next();
}

module.exports = sessionMiddleware;

// Made with Bob
```

---

## Regression Test Suite

### Test File: test/memory-leak.test.js

```javascript
const request = require('supertest');
const app = require('../server');

describe('Memory Leak Regression Tests', () => {
  
  describe('sessionCache bounded growth', () => {
    it('should not exceed 1000 entries in sessionCache', async () => {
      // Send 1500 payment requests
      const promises = [];
      for (let i = 0; i < 1500; i++) {
        promises.push(
          request(app)
            .post('/payment')
            .send({ userId: `user_${i}`, amount: 100 })
        );
      }
      
      await Promise.all(promises);
      
      // Check metrics endpoint
      const response = await request(app).get('/metrics');
      expect(response.status).toBe(200);
      expect(response.body.cache.size).toBeLessThanOrEqual(1000);
    });
    
    it('should evict old entries when cache is full', async () => {
      // Fill cache to max
      for (let i = 0; i < 1000; i++) {
        await request(app)
          .post('/payment')
          .send({ userId: `user_${i}`, amount: 100 });
      }
      
      const beforeSize = (await request(app).get('/metrics')).body.cache.size;
      
      // Add 100 more entries
      for (let i = 1000; i < 1100; i++) {
        await request(app)
          .post('/payment')
          .send({ userId: `user_${i}`, amount: 100 });
      }
      
      const afterSize = (await request(app).get('/metrics')).body.cache.size;
      
      // Cache size should remain at max (1000)
      expect(beforeSize).toBe(1000);
      expect(afterSize).toBe(1000);
    });
  });
  
  describe('SessionStore TTL cleanup', () => {
    it('should remove expired sessions after TTL', async () => {
      // Create session with short TTL (for testing)
      const sessionStore = require('../store/sessionStore');
      const originalTTL = sessionStore.sessionTTL;
      sessionStore.sessionTTL = 1000; // 1 second for test
      
      // Create session
      await request(app)
        .post('/payment/process')
        .set('x-session-id', 'test-session-123')
        .send({ userId: 'user1', amount: 100, currency: 'USD' });
      
      expect(sessionStore.size()).toBeGreaterThan(0);
      
      // Wait for TTL + cleanup interval
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Trigger cleanup
      sessionStore.cleanup();
      
      // Session should be removed
      expect(sessionStore.get('test-session-123')).toBeUndefined();
      
      // Restore original TTL
      sessionStore.sessionTTL = originalTTL;
    });
    
    it('should enforce max session limit', async () => {
      const sessionStore = require('../store/sessionStore');
      const maxSize = sessionStore.maxSize;
      
      // Create sessions up to max + 100
      for (let i = 0; i < maxSize + 100; i++) {
        await request(app)
          .post('/payment/process')
          .set('x-session-id', `session-${i}`)
          .send({ userId: `user${i}`, amount: 100, currency: 'USD' });
      }
      
      // Store size should not exceed maxSize
      expect(sessionStore.size()).toBeLessThanOrEqual(maxSize);
    });
  });
  
  describe('Memory stability under load', () => {
    it('should maintain stable memory usage over 1000 requests', async () => {
      const initialMetrics = await request(app).get('/metrics');
      const initialHeap = initialMetrics.body.memory.heapUsed;
      
      // Send 1000 requests
      const promises = [];
      for (let i = 0; i < 1000; i++) {
        promises.push(
          request(app)
            .post('/payment')
            .send({ userId: `user_${i}`, amount: 100 })
        );
      }
      await Promise.all(promises);
      
      // Force garbage collection if available
      if (global.gc) {
        global.gc();
      }
      
      const finalMetrics = await request(app).get('/metrics');
      const finalHeap = finalMetrics.body.memory.heapUsed;
      
      // Memory growth should be bounded (less than 50MB increase)
      const growthMB = (finalHeap - initialHeap) / (1024 * 1024);
      expect(growthMB).toBeLessThan(50);
    });
  });
});
```

### Test Dependencies (package.json)
```json
{
  "devDependencies": {
    "jest": "^29.0.0",
    "supertest": "^6.3.0"
  },
  "scripts": {
    "test": "jest",
    "test:memory": "node --expose-gc node_modules/.bin/jest test/memory-leak.test.js"
  }
}
```

### Installation Commands
```bash
cd demo-service3
npm install --save-dev jest@^29.0.0 supertest@^6.3.0
```

---

## Deployment Steps

### 1. Install Dependencies
```bash
cd demo-service3
npm install lru-cache@^10.0.0
npm install --save-dev jest@^29.0.0 supertest@^6.3.0
```

### 2. Apply Code Changes
- Replace `server.js` lines 1-15 with LRU cache implementation
- Replace entire `store/sessionStore.js` file
- Replace entire `middleware/session.js` file
- Create `test/memory-leak.test.js` with regression tests

### 3. Run Tests
```bash
npm run test:memory
```

### 4. Verify Memory Stability
```bash
# Start service
npm start

# In another terminal, run load test
for i in {1..2000}; do
  curl -X POST http://localhost:3001/payment \
    -H "Content-Type: application/json" \
    -d '{"userId":"user'$i'","amount":100}'
done

# Check metrics
curl http://localhost:3001/metrics
```

### 5. Monitor in Production
- Watch heap growth rate (should stabilize after initial warmup)
- Monitor cache size (should not exceed 1000)
- Monitor session count (should not exceed 10000)
- Alert if heap growth > 10MB/minute sustained

---

## Environment Variables (Optional Configuration)

Add to `.env` or deployment config:
```bash
# SessionStore configuration
SESSION_MAX_SIZE=10000              # Maximum sessions in memory
SESSION_TTL_MS=1800000              # 30 minutes session lifetime
SESSION_CLEANUP_INTERVAL_MS=60000   # 1 minute cleanup interval

# Memory monitoring
MEMORY_ALERT_THRESHOLD_MB=250       # Alert threshold (existing)
```

---

## Rollback Plan

If issues occur after deployment:

1. **Immediate**: Restart service (clears memory)
2. **Quick rollback**: Revert to previous commit
3. **Monitoring**: Check for:
   - Increased error rates
   - Session-related failures
   - Cache miss rates

---

## Success Criteria

✅ **Memory Growth**: Heap usage stabilizes under sustained load  
✅ **Cache Size**: sessionCache never exceeds 1000 entries  
✅ **Session Count**: SessionStore never exceeds 10000 sessions  
✅ **Tests Pass**: All regression tests pass  
✅ **No Functional Regression**: Payment processing continues to work  
✅ **Performance**: No significant latency increase (<5ms p99)

---

## Post-Deployment Validation

### Week 1: Monitor closely
- Check memory metrics every 4 hours
- Review logs for eviction patterns
- Validate no session-related errors

### Week 2-4: Standard monitoring
- Weekly memory trend analysis
- Compare pre/post fix metrics
- Document lessons learned

---

## Documentation Updates

Update the following files:
1. `README.md` - Add memory management section
2. `ARCHITECTURE.md` - Document cache strategy
3. Service runbook - Add memory troubleshooting steps
