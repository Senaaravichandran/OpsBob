// Load Generator - Simulates high-frequency payment requests to trigger memory leak.
// Sends POST requests every 200ms to demonstrate how the sessionCache grows unbounded.
const http = require('http');

// Configuration
const TARGET_HOST = 'localhost';
const TARGET_PORT = 3001;
const REQUEST_INTERVAL = 200; // milliseconds

let requestCount = 0;

/**
 * Generate random user ID (4-digit number)
 */
function generateUserId() {
  return Math.floor(1000 + Math.random() * 9000);
}

/**
 * Generate random payment amount (float between 10.00 and 999.99)
 */
function generateAmount() {
  return parseFloat((10 + Math.random() * 989.99).toFixed(2));
}

/**
 * Send a single payment request
 */
function sendPaymentRequest() {
  requestCount++;
  
  const payload = {
    userId: generateUserId(),
    amount: generateAmount()
  };
  
  const postData = JSON.stringify(payload);
  
  const options = {
    hostname: TARGET_HOST,
    port: TARGET_PORT,
    path: '/payment',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData)
    }
  };
  
  const req = http.request(options, (res) => {
    let data = '';
    
    res.on('data', (chunk) => {
      data += chunk;
    });
    
    res.on('end', () => {
      if (res.statusCode === 200) {
        console.log(`Sent request #${requestCount} — Memory will grow`);
      } else {
        console.log(`Request #${requestCount} failed with status ${res.statusCode}`);
      }
    });
  });
  
  req.on('error', (error) => {
    console.error(`Request #${requestCount} error:`, error.message);
  });
  
  req.write(postData);
  req.end();
}

/**
 * Start the load generator
 */
function startLoadGenerator() {
  console.log('='.repeat(60));
  console.log('Load Generator Started');
  console.log('='.repeat(60));
  console.log(`Target: http://${TARGET_HOST}:${TARGET_PORT}/payment`);
  console.log(`Interval: ${REQUEST_INTERVAL}ms per request`);
  console.log(`Expected rate: ${1000 / REQUEST_INTERVAL} requests/second`);
  console.log('='.repeat(60));
  console.log('');
  
  // Send requests at regular intervals
  setInterval(() => {
    sendPaymentRequest();
  }, REQUEST_INTERVAL);
  
  // Send first request immediately
  sendPaymentRequest();
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('');
  console.log('='.repeat(60));
  console.log(`Load generator stopped after ${requestCount} requests`);
  console.log('='.repeat(60));
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('');
  console.log('='.repeat(60));
  console.log(`Load generator stopped after ${requestCount} requests`);
  console.log('='.repeat(60));
  process.exit(0);
});

// Start the load generator
startLoadGenerator();

// Made with Bob
