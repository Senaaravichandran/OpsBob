// In-memory session store with memory leak bug
// BUG: Sessions are never cleaned up, causing unbounded memory growth

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
    
    // BUG: No cleanup mechanism!
    // Sessions accumulate indefinitely in memory
    // Should implement TTL-based cleanup or LRU eviction
  }
  
  delete(sessionId) {
    return this.sessions.delete(sessionId);
  }
  
  size() {
    return this.sessions.size;
  }
  
  // Missing: cleanup method to remove expired sessions
  // Missing: TTL configuration
  // Missing: max size limit
}

// Export singleton instance
module.exports = new SessionStore();

// Made with Bob
