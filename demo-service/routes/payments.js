// Payment processing routes
const express = require('express');
const router = express.Router();
const sessionMiddleware = require('../middleware/session');

// Apply session middleware to all payment routes
router.use(sessionMiddleware);

// Process payment endpoint
router.post('/process', async (req, res) => {
  const { amount, currency, userId } = req.body;
  
  try {
    // Validate payment data
    if (!amount || !currency || !userId) {
      return res.status(400).json({ error: 'Missing required fields' });
    }
    
    // Process payment (simulated)
    const paymentId = `pay_${Date.now()}_${userId}`;
    
    // Store payment in session for tracking
    req.session.lastPayment = {
      id: paymentId,
      amount,
      currency,
      userId,
      timestamp: Date.now()
    };
    
    console.log(`Payment processed: ${paymentId}`);
    
    res.json({
      success: true,
      paymentId,
      amount,
      currency
    });
    
  } catch (error) {
    console.error('Payment processing error:', error);
    res.status(500).json({ error: 'Payment processing failed' });
  }
});

// Get payment status
router.get('/status/:paymentId', (req, res) => {
  const { paymentId } = req.params;
  
  // Check if payment exists in session
  if (req.session.lastPayment && req.session.lastPayment.id === paymentId) {
    res.json({
      status: 'completed',
      payment: req.session.lastPayment
    });
  } else {
    res.status(404).json({ error: 'Payment not found' });
  }
});

module.exports = router;

// Made with Bob
