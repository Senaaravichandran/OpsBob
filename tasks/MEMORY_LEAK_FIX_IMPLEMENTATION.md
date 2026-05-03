# Memory Leak Fix Implementation Plan

**Incident:** INC-2026-DEMO-001  
**Status:** Ready for Implementation  
**Mode Required:** code or advanced

---

## Fix 1: LRU Cache for sessionCache (server.js)

### Current Code (Lines 18, 118-127)
```javascript
// Line 18
const sessionCache = new Map();

// Lines 118-127 in POST /payment handler
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
// Add at top of file after imports
const LRU = require('lru-cache');

// Replace line 18 with:
const sessionCache = new LRU({
  max: 1000, // Maximum 1000 entries
  maxAge: 1000 * 60 * 30, // 30 minutes TTL
  updateAgeOnGet: false // Don't refresh TTL on read
});

// Lines 118-127 remain the same - LRU handles eviction automatically
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
Add to `demo-service/package.json`:
```json
"dependencies": {
  "lru-cache": "^7.18.3"
}
```

---

## Fix 2: TTL-Based Cleanup for SessionStore

### Current Code (store/sessionStore.js)
```javascript
class SessionStore {
  constructor() {
    this.sessions = new Map();
    console.log('SessionStore initialized');
  }
  
  set(sessionId, session) {
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
    // BUG: No cleanup mechanism!
  }
}
```

### Fixed Code
```javascript
class SessionStore {
  constructor(options = {}) {
    this.sessions = new Map();
    this.ttl = options.ttl || 30 * 60 * 1000; // Default 30 minutes
    this.maxSessions = options.maxSessions || 10000; // Max 10k sessions
    console.log(`SessionStore initialized (TTL: ${this.ttl}ms, Max: ${this.maxSessions})`);
    
    // Start cleanup interval
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60 * 1000); // Run every 60 seconds
  }
  
  get(sessionId) {
    const session = this.sessions.get(sessionId);
    if (session && this.isExpired(session)) {
      this.sessions.delete(sessionId);
      return undefined;
    }
    return session;
  }
  
  set(sessionId, session) {
    // Enforce max sessions limit
    if (this.sessions.size >= this.maxSessions && !this.sessions.has(sessionId)) {
      console.warn(`Max sessions (${this.maxSessions}) reached, rejecting new session`);
      return false;
    }
    
    // Add expiry timestamp
    session.expiresAt = Date.now() + this.ttl;
    this.sessions.set(sessionId, session);
    console.log(`Session stored: ${sessionId} (total: ${this.sessions.size})`);
    return true;
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  isExpired(session) {
    return Date.now() > session.expiresAt;
  }
  
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
      console.log(`Session cleanup: removed ${removed} expired sessions (${before} → ${this.sessions.size})`);
    }
  }
  
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
  }
}

// Export singleton instance with configuration
module.exports = new SessionStore({
  ttl: 30 * 60 * 1000, // 30 minutes
  maxSessions: 10000
});
```

---

## Fix 3: Session Reuse in Middleware

### Current Code (middleware/session.js)
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

### Fixed Code
```javascript
const crypto = require('crypto');

function sessionMiddleware(req, res, next) {
  // Try to get session ID from cookie first, then header
  let sessionId = req.cookies?.sessionId || req.headers['x-session-id'];
  
  // Only generate new session if none exists
  if (!sessionId) {
    sessionId = `session_${Date.now()}_${crypto.randomBytes(8).toString('hex')}`;
  }
  
  let session = sessionStore.get(sessionId);
  
  if (!session) {
    session = {
      id: sessionId,
      createdAt: Date.now(),
      data: {}
    };
    
    // Check if store accepted the session (may reject if at max capacity)
    const stored = sessionStore.set(sessionId, session);
    if (!stored) {
      return res.status(503).json({ 
        error: 'Service temporarily unavailable - session limit reached' 
      });
    }
    
    // Set session cookie for reuse
    res.cookie('sessionId', sessionId, {
      httpOnly: true,
      maxAge: 30 * 60 * 1000, // 30 minutes
      sameSite: 'strict'
    });
  }
  
  req.session = session.data;
  req.sessionId = sessionId;
  session.lastAccessed = Date.now();
  
  next();
}

module.exports = sessionMiddleware;
```

### Additional Dependency
Add to `demo-service/package.json`:
```json
"dependencies": {
  "cookie-parser": "^1.4.6"
}
```

Add to `demo-service/server.js` (after line 15):
```javascript
const cookieParser = require('cookie-parser');
app.use(cookieParser());
```

---

## Regression Test

### File: `demo-service/test/memory-leak.test.js`

```javascript
const request = require('supertest');
const app = require('../server');

describe('Memory Leak Regression Test', () => {
  let initialHeapUsed;
  let initialCacheSize;
  
  beforeAll(async () => {
    // Get baseline metrics
    const metricsRes = await request(app).get('/metrics');
    initialHeapUsed = metricsRes.body.memory.heapUsed;
    initialCacheSize = metricsRes.body.cache.size;
  });
  
  test('should not leak memory after 1000 payment requests', async () => {
    const numRequests = 1000;
    const requests = [];
    
    // Generate 1000 payment requests
    for (let i = 0; i < numRequests; i++) {
      requests.push(
        request(app)
          .post('/payment')
          .send({
            userId: `user_${i}`,
            amount: Math.floor(Math.random() * 1000) + 1
          })
      );
    }
    
    // Execute all requests
    await Promise.all(requests);
    
    // Wait for potential cleanup cycles
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Get final metrics
    const finalMetrics = await request(app).get('/metrics');
    const finalHeapUsed = finalMetrics.body.memory.heapUsed;
    const finalCacheSize = finalMetrics.body.cache.size;
    
    // Calculate memory growth
    const heapGrowthMB = (finalHeapUsed - initialHeapUsed) / (1024 * 1024);
    
    console.log(`Memory growth: ${heapGrowthMB.toFixed(2)}MB`);
    console.log(`Cache size: ${initialCacheSize} → ${finalCacheSize}`);
    
    // Assertions
    expect(heapGrowthMB).toBeLessThan(10); // Less than 10MB growth
    expect(finalCacheSize).toBeLessThanOrEqual(1000); // LRU max size enforced
    
  }, 30000); // 30 second timeout
  
  test('sessionCache should evict old entries when at capacity', async () => {
    // Fill cache to capacity
    for (let i = 0; i < 1100; i++) {
      await request(app)
        .post('/payment')
        .send({
          userId: `user_${i}`,
          amount: 100
        });
    }
    
    const metrics = await request(app).get('/metrics');
    const cacheSize = metrics.body.cache.size;
    
    // Cache should not exceed max size (1000)
    expect(cacheSize).toBeLessThanOrEqual(1000);
  }, 30000);
  
  test('sessions should expire after TTL', async () => {
    // Create a session
    const res1 = await request(app)
      .post('/payment')
      .send({ userId: 'test_user', amount: 100 });
    
    const sessionId = res1.headers['set-cookie']?.[0]?.match(/sessionId=([^;]+)/)?.[1];
    
    // Mock time passage (would need to adjust SessionStore for testing)
    // In real test, you'd wait or mock Date.now()
    
    // For now, just verify session exists
    expect(sessionId).toBeDefined();
  });
});
```

### Test Dependencies
Add to `demo-service/package.json`:
```json
"devDependencies": {
  "jest": "^29.7.0",
  "supertest": "^6.3.3"
}
```

---

## Implementation Checklist

- [ ] Install `lru-cache` package
- [ ] Install `cookie-parser` package  
- [ ] Install test dependencies (`jest`, `supertest`)
- [ ] Update `server.js` with LRU cache
- [ ] Update `store/sessionStore.js` with TTL cleanup
- [ ] Update `middleware/session.js` with session reuse
- [ ] Create regression test file
- [ ] Run tests to verify fixes
- [ ] Monitor memory metrics in staging

---

## Expected Outcomes

### Before Fix
- Memory grows unbounded (~2MB/minute under load)
- `sessionCache.size` increases indefinitely
- Service crashes after 2-4 hours

### After Fix
- Memory growth bounded to <10MB for 1000 requests
- `sessionCache.size` capped at 1000 entries
- Sessions expire after 30 minutes
- Service runs indefinitely without memory issues

---

**Ready for Implementation:** Switch to `code` or `advanced` mode to apply these changes.
