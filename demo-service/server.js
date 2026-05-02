// Demo Payment Service - Express.js API with intentional memory leak for OpsBob demonstration.
// Simulates a production bug where sessionCache grows unbounded, triggering Instana alerts.
const express = require('express');
const app = express();

// Configuration from environment variables with fallbacks
const PORT = process.env.PORT || 3000;

// Middleware to parse JSON request bodies
app.use(express.json());

// BUG: sessionCache grows indefinitely — never evicted
const sessionCache = new Map();

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
 * Payment processing endpoint
 * Simulates payment processing with intentional memory leak
 * 
 * Request body: { userId: string, amount: number }
 * Response: { transactionId: string, status: string }
 */
app.post('/payment', (req, res) => {
  try {
    const { userId, amount } = req.body;
    
    // Validate required fields
    if (!userId || amount === undefined) {
      return res.status(400).json({
        status: 'error',
        message: 'Missing required fields: userId and amount'
      });
    }
    
    // Validate amount is a positive number
    if (typeof amount !== 'number' || amount <= 0) {
      return res.status(400).json({
        status: 'error',
        message: 'Amount must be a positive number'
      });
    }
    
    // Generate unique transaction ID
    const transactionId = `txn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // INTENTIONAL MEMORY LEAK: Store full request in cache that never gets cleared
    // This simulates a common bug where session/cache data accumulates over time
    sessionCache.set(Date.now(), {
      userId,
      amount,
      transactionId,
      timestamp: new Date().toISOString(),
      requestBody: req.body,
      headers: req.headers,
      ip: req.ip
    });
    
    // Log for debugging (in production, this would go to proper logging service)
    console.log(`Payment processed: ${transactionId} for user ${userId}, amount: ${amount}`);
    console.log(`Cache size: ${sessionCache.size} entries`);
    
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
    service: 'demo-service',
    version: '1.0.0',
    description: 'Payment processing microservice for OpsBob demo',
    endpoints: {
      health: 'GET /health',
      payment: 'POST /payment'
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
  console.log(`Payment endpoint: http://localhost:${PORT}/payment`);
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`);
});

/**
 * Graceful shutdown handler
 */
process.on('SIGTERM', () => {
  console.log('SIGTERM signal received: closing HTTP server');
  server.close(() => {
    console.log('HTTP server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('SIGINT signal received: closing HTTP server');
  server.close(() => {
    console.log('HTTP server closed');
    process.exit(0);
  });
});

module.exports = app;

// Made with Bob
