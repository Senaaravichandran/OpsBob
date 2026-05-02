#!/bin/bash
# OpsBob Startup Script
# Validates environment and starts all required services

set -e  # Exit on any error

echo "=========================================="
echo "OpsBob System Startup"
echo "=========================================="
echo ""

# ============================================================================
# Environment Variable Validation
# ============================================================================
echo "[1/4] Validating environment variables..."

REQUIRED_VARS=(
    "BOB_API_KEY"
    "BOB_API_URL"
    "INSTANA_BASE_URL"
    "INSTANA_API_TOKEN"
    "IBM_CLOUD_API_KEY"
    "IBM_CLOUD_REGION"
    "CODE_ENGINE_PROJECT"
    "ICR_NAMESPACE"
    "CODE_ENGINE_APP_NAME"
    "SOURCE_FILES_PATH"
)

MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "❌ ERROR: Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please set these variables in your .env file or export them."
    echo "See .env.example for reference."
    exit 1
fi

echo "✓ All required environment variables are set"
echo ""

# ============================================================================
# Validate Required Files and Directories
# ============================================================================
echo "[2/4] Validating required files..."

# Check if MCP server is built
if [ ! -f "mcp-server/dist/index.js" ]; then
    echo "❌ ERROR: MCP server not built"
    echo "Run: cd mcp-server && npm install && npm run build"
    exit 1
fi

# Check if source files directory exists
if [ ! -d "$SOURCE_FILES_PATH" ]; then
    echo "❌ ERROR: Source files directory not found: $SOURCE_FILES_PATH"
    exit 1
fi

# Check if backend exists
if [ ! -f "backend/main.py" ]; then
    echo "❌ ERROR: Backend not found: backend/main.py"
    exit 1
fi

echo "✓ All required files present"
echo ""

# ============================================================================
# Start MCP Server
# ============================================================================
echo "[3/4] Starting Instana MCP server..."

# Kill any existing MCP server process
pkill -f "node.*mcp-server/dist/index.js" 2>/dev/null || true

# Start MCP server in background
cd mcp-server
node dist/index.js > ../mcp-server.log 2>&1 &
MCP_PID=$!
cd ..

# Wait a moment for MCP server to start
sleep 2

# Check if MCP server is still running
if ! ps -p $MCP_PID > /dev/null; then
    echo "❌ ERROR: MCP server failed to start"
    echo "Check mcp-server.log for details"
    exit 1
fi

echo "✓ MCP server started (PID: $MCP_PID)"
echo "  Log file: mcp-server.log"
echo ""

# ============================================================================
# Start FastAPI Backend
# ============================================================================
echo "[4/4] Starting FastAPI backend..."

# Get backend port from env or use default
BACKEND_PORT=${BACKEND_PORT:-8000}

# Kill any existing backend process on the port
lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true

# Start backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --reload > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo "  Waiting for backend to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ ERROR: Backend failed to start within 30 seconds"
    echo "Check backend.log for details"
    kill $MCP_PID 2>/dev/null || true
    exit 1
fi

echo "✓ Backend started (PID: $BACKEND_PID)"
echo "  Log file: backend.log"
echo ""

# ============================================================================
# Startup Complete
# ============================================================================
echo "=========================================="
echo "✓ OpsBob System Ready"
echo "=========================================="
echo ""
echo "Backend API:     http://localhost:$BACKEND_PORT"
echo "Health Check:    http://localhost:$BACKEND_PORT/health"
echo "Webhook Endpoint: http://localhost:$BACKEND_PORT/webhook"
echo ""
echo "Configure Instana webhook to POST to:"
echo "  http://your-server:$BACKEND_PORT/webhook"
echo ""
echo "Process IDs:"
echo "  MCP Server: $MCP_PID"
echo "  Backend:    $BACKEND_PID"
echo ""
echo "To stop all services, run:"
echo "  kill $MCP_PID $BACKEND_PID"
echo ""
echo "Logs:"
echo "  MCP Server: tail -f mcp-server.log"
echo "  Backend:    tail -f backend.log"
echo ""
echo "Press Ctrl+C to stop monitoring (services will continue running)"
echo "=========================================="

# Keep script running and show logs
tail -f backend.log

# Made with Bob
