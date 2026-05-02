// Test suite for sessionStore
const assert = require('assert');

describe('SessionStore', () => {
  let sessionStore;
  
  beforeEach(() => {
    // Clear require cache to get fresh instance
    delete require.cache[require.resolve('../store/sessionStore')];
    sessionStore = require('../store/sessionStore');
  });
  
  it('should store and retrieve sessions', () => {
    const sessionId = 'test-session-1';
    const sessionData = {
      id: sessionId,
      createdAt: Date.now(),
      data: { userId: 'user123' }
    };
    
    sessionStore.set(sessionId, sessionData);
    const retrieved = sessionStore.get(sessionId);
    
    assert.strictEqual(retrieved.id, sessionId);
    assert.strictEqual(retrieved.data.userId, 'user123');
  });
  
  it('should return undefined for non-existent sessions', () => {
    const result = sessionStore.get('non-existent');
    assert.strictEqual(result, undefined);
  });
  
  it('should delete sessions', () => {
    const sessionId = 'test-session-2';
    sessionStore.set(sessionId, { id: sessionId });
    
    const deleted = sessionStore.delete(sessionId);
    assert.strictEqual(deleted, true);
    
    const retrieved = sessionStore.get(sessionId);
    assert.strictEqual(retrieved, undefined);
  });
  
  it('should track session count', () => {
    const initialSize = sessionStore.size();
    
    sessionStore.set('session-1', { id: 'session-1' });
    sessionStore.set('session-2', { id: 'session-2' });
    
    assert.strictEqual(sessionStore.size(), initialSize + 2);
  });
});

// Made with Bob
