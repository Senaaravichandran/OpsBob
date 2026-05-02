#!/bin/bash
# Demo Trigger Script - Starts the payment service, load generator, and fires mock Instana webhook.
# Orchestrates the full OpsBob demo flow from incident creation to resolution.
#!/bin/bash

echo "🚀 Starting OpsBob Demo..."
echo ""

# 1. Start the demo-service in background
echo "📦 Starting demo-service (payments-api)..."
cd demo-service && node server.js &
DEMO_SERVICE_PID=$!
cd ..
echo "   PID: $DEMO_SERVICE_PID"

# 2. Wait 2 seconds
sleep 2

# 3. Start the load generator in background
echo "⚡ Starting load generator..."
node demo-service/load-generator.js &
LOAD_GEN_PID=$!
echo "   PID: $LOAD_GEN_PID"

# 4. Wait 3 seconds
sleep 3

# 5. Fire the mock Instana webhook
echo "🔔 Triggering mock incident via webhook..."
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"service":"payments-api","severity":"HIGH","type":"MEMORY_LEAK","incidentId":"INC-2024-001","startTime":"2024-05-02T02:14:00Z","message":"Memory usage growing at 45MB/min, threshold exceeded"}'

echo ""
echo ""
echo "✅ Demo triggered!"
echo "📊 Open http://localhost:3000 to see OpsBob in action"
echo ""
echo "Process IDs:"
echo "  Demo Service: $DEMO_SERVICE_PID"
echo "  Load Generator: $LOAD_GEN_PID"
echo ""
echo "To stop the demo, run: bash stop-demo.sh"

# Made with Bob
