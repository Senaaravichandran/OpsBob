#!/bin/bash
# Demo Stop Script - Terminates all OpsBob demo processes (payment service and load generator).
# Cleans up background Node.js processes started by demo-trigger.sh.
#!/bin/bash

echo "🛑 Stopping OpsBob Demo..."
echo ""

# Kill all node processes (demo-service and load-generator)
echo "Stopping Node.js processes..."
pkill -f "node server.js"
pkill -f "node.*load-generator.js"

# Alternative: Kill by port if needed
# lsof -ti:3001 | xargs kill -9 2>/dev/null

echo "✅ Demo stopped"
echo ""
echo "All background processes terminated."

# Made with Bob
