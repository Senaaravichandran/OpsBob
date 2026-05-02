// Demo Payment Service - Express.js API with intentional memory leak for OpsBob demonstration.
// Simulates a production bug where sessionCache grows unbounded, triggering Instana alerts.
const express = require('express');
const app = express();

// Import metrics and traces modules
const { getMetrics, getPrometheusMetrics, trackRequest, trackError } = require('./metrics');
const { captureTrace, captureError, captureMemoryLeakTrace, getTraces } = require('./debug/traces');

// Configuration from environment variables with fallbacks
const PORT = process.env.PORT || 3001;
const MEMORY_ALERT_THRESHOLD_MB = parseInt(process.env.MEMORY_ALERT_THRESHOLD_MB || '250');

// Middleware to parse JSON request bodies
app.use(express.json());

// BUG: sessionCache grows indefinitely — never evicted
const sessionCache = new Map();

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
 * Simulates payment processing with intentional memory leak
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

    // Capture trace periodically to show the leak accumulating
    if (sessionCache.size % 100 === 0) {
      captureTrace('payment_handler', {
        cache_size: sessionCache.size,
        transaction_id: transactionId,
        user_id: userId
      });
    }
    
    // Log for debugging (in production, this would go to proper logging service)
    if (sessionCache.size % 50 === 0) {
      console.log(`Payment processed: ${transactionId} | Cache size: ${sessionCache.size} entries`);
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
    version: '1.0.0',
    description: 'Payment processing microservice for OpsBob demo',
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

// Made with Bob
