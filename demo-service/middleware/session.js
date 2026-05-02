// Session middleware with memory leak bug
const sessionStore = require('../store/sessionStore');

function sessionMiddleware(req, res, next) {
  const sessionId = req.headers['x-session-id'] || `session_${Date.now()}_${Math.random()}`;
  
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
  
  // Update last accessed time
  session.lastAccessed = Date.now();
  
  next();
}

module.exports = sessionMiddleware;

// Made with Bob
