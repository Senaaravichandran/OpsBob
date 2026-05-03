# Root Cause Analysis: INC-TEST-001

## Incident Summary
- **Service**: demo-service
- **Incident ID**: INC-TEST-001
- **Severity**: HIGH
- **Type**: MEMORY_LEAK
- **Detection**: Memory growth over 10 minutes

---

## Root Cause Identification

### Primary Memory Leak
**File**: `demo-service/server.js`  
**Variable**: `sessionCache`  
**Line**: 18  
**Code**: `const sessionCache = new Map();`

**Issue**: The `sessionCache` Map stores every payment transaction using `Date.now()` as keys (line 109) but implements **zero eviction strategy**. Each POST to `/payment` adds an entry that persists for the application's lifetime, causing unbounded linear memory growth.

### Secondary Memory Leaks
1. **File**: `demo-service/store/sessionStore.js`  
   **Variable**: `this.sessions`  
   **Line**: 6  
   **Issue**: Sessions Map lacks TTL, LRU eviction, or size limits

2. **File**: `demo-service/middleware/session.js`  
   **Line**: 10-16  
   **Issue**: Creates new sessions without cleanup; `lastAccessed` timestamp never used for GC

---

## Fix Plan (3 Bullet Points)

1. **Implement TTL-based eviction for `sessionCache` in server.js**: Add a cleanup interval that removes entries older than 5 minutes (configurable via `SESSION_TTL_MS` env var), and store `{ timestamp, data }` objects instead of raw data to enable age-based filtering during periodic sweeps.

2. **Replace SessionStore Map with LRU cache**: Integrate `lru-cache` npm package (or implement custom LRU) with max 10,000 entries and 30-minute TTL, ensuring automatic eviction of least-recently-used sessions when capacity is reached or entries expire.

3. **Add session cleanup scheduler in middleware**: Implement a background interval (every 60 seconds) that iterates through `sessionStore.sessions` and deletes entries where `Date.now() - session.lastAccessed > TTL_MS`, ensuring the `lastAccessed` field serves its intended purpose.

---

## Regression Test Specification

**Test Name**: `test_memory_leak_prevention`  
**Objective**: Verify that sessionCache and SessionStore do not grow unbounded under sustained load

**Test Steps**:
1. Capture baseline memory usage via `/health` endpoint
2. Send 1,000 POST requests to `/payment` with unique userIds
3. Wait for cleanup interval to execute (6+ minutes for TTL expiration)
4. Capture post-cleanup memory usage
5. **Assert**: Memory growth < 10MB (accounting for V8 overhead)
6. **Assert**: `sessionCache.size` < 100 (most entries should be evicted)
7. **Assert**: `sessionStore.size()` < 100

**Expected Behavior**: Memory stabilizes after cleanup cycles, proving bounded growth.

---

## Impact Analysis
- **Affected Endpoints**: `/payment` (primary), all routes using session middleware (secondary)
- **Data Loss Risk**: None (sessions are ephemeral by design)
- **Deployment Risk**: Low (additive changes, backward compatible)
- **Performance Impact**: Minimal (cleanup runs in background, O(n) scan every 60s)

---

## Next Steps
1. Get approval for fix approach
2. Switch to code mode for implementation
3. Implement fixes in order: sessionCache → SessionStore → middleware
4. Write and execute regression test
5. Deploy to staging for validation
6. Monitor memory metrics post-deployment
