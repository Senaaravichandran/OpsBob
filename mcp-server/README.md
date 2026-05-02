# MCP Instana Server

Model Context Protocol (MCP) server that simulates IBM Instana's incident API for OpsBob hackathon demo. This server provides hardcoded monitoring data to demonstrate OpsBob's ability to detect and diagnose a memory leak in the demo-service.

## Overview

This MCP server exposes three tools that return realistic but hardcoded incident data, metrics, and stack traces. It's designed specifically for demo purposes and does not connect to any real monitoring system.

## Installation

```bash
cd mcp-server
npm install
npm run build
```

## Usage

### Running the Server

```bash
npm start
```

The server runs on stdio transport, which is the standard MCP pattern for integration with AI assistants.

### Development Mode

```bash
npm run dev
```

## MCP Tools

### 1. get_active_incidents

Returns a list of active incidents from the monitoring system.

**Input:** None

**Output:**
```json
[
  {
    "id": "INC-2024-001",
    "service": "payments-api",
    "severity": "HIGH",
    "type": "MEMORY_LEAK",
    "startTime": "2024-05-02T02:14:00Z",
    "message": "Memory usage growing at 45MB/min, threshold exceeded"
  }
]
```

**Purpose:** Provides the initial alert that triggers OpsBob's investigation.

### 2. get_service_metrics

Returns service metrics over a specified time window.

**Input:**
```json
{
  "serviceName": "payments-api",
  "windowMinutes": 10
}
```

**Output:**
```json
{
  "service": "payments-api",
  "memoryMB": [128, 156, 189, 224, 267, 310, 340],
  "timestamps": [
    "2024-05-02T02:14:00Z",
    "2024-05-02T02:15:00Z",
    "2024-05-02T02:16:00Z",
    "2024-05-02T02:17:00Z",
    "2024-05-02T02:18:00Z",
    "2024-05-02T02:19:00Z",
    "2024-05-02T02:20:00Z"
  ],
  "status": "degraded",
  "windowMinutes": 10
}
```

**Purpose:** Shows the memory leak progression from 128MB to 340MB over 7 minutes, demonstrating a clear upward trend at ~45MB/min.

### 3. get_stack_traces

Returns stack traces for a specific incident.

**Input:**
```json
{
  "incidentId": "INC-2024-001"
}
```

**Output:**
```json
{
  "incidentId": "INC-2024-001",
  "service": "payments-api",
  "stackTrace": "Error: Heap out of memory\n    at Map.set (native)\n    at sessionCache.set (/app/server.js:18:15)\n    at app.post /payment (/app/server.js:24:3)\n    at Layer.handle [as handle_request] (/app/node_modules/express/lib/router/layer.js:95:5)\n    at next (/app/node_modules/express/lib/router/route.js:144:13)\n    at Route.dispatch (/app/node_modules/express/lib/router/route.js:114:3)\n    at Layer.handle [as handle_request] (/app/node_modules/express/lib/router/layer.js:95:5)\n    at /app/node_modules/express/lib/router/index.js:284:15\n    at Function.process_params (/app/node_modules/express/lib/router/index.js:346:12)\n    at next (/app/node_modules/express/lib/router/index.js:280:10)",
  "timestamp": "2024-05-02T02:20:15Z"
}
```

**Purpose:** Points directly to the bug location: `sessionCache.set (/app/server.js:18:15)` - the line where sessions are stored without expiration, causing the memory leak.

## Hardcoded Data Structure

All data is hardcoded for demo safety and consistency:

- **Incident ID:** `INC-2024-001`
- **Service Name:** `payments-api`
- **Memory Growth:** 128MB → 340MB (45MB/min)
- **Bug Location:** `/app/server.js:18:15` (sessionCache.set)
- **Time Window:** 7 data points over ~6 minutes

## Integration with OpsBob

OpsBob uses these three tools in sequence:

1. **get_active_incidents** - Discovers the memory leak incident
2. **get_service_metrics** - Analyzes the memory growth pattern
3. **get_stack_traces** - Identifies the exact code location causing the leak

The stack trace points to line 18 in `demo-service/server.js`, where the session cache stores data without expiration:

```javascript
// Line 18 in demo-service/server.js - THE BUG
sessionCache.set(sessionId, { userId, timestamp: Date.now() });
```

## Error Handling

The server includes try/catch blocks and returns proper error responses:

```json
{
  "error": "Error message here"
}
```

## Configuration

The server uses environment variables for configuration (if needed in future):

- Currently no configuration required
- All data is hardcoded for demo purposes

## Architecture

- **Transport:** stdio (standard MCP pattern)
- **SDK:** `@modelcontextprotocol/sdk` v1.0.0
- **Language:** TypeScript (ES2020)
- **Module System:** ES Modules

## Demo Safety

This server is designed to be demo-safe:

- No external API calls
- No database connections
- All responses are hardcoded
- Predictable behavior for live demos
- Fast response times

## License

MIT