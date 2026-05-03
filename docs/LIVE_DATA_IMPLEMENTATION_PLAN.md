# OpsBob Live Data Implementation Plan

## Overview
Transform OpsBob from demo with hardcoded data to production system using real runtime data from Instana, live source code, and actual IBM Cloud deployments.

---

## 1. INSTANA MCP SERVER CHANGES

### File: `mcp-server/src/index.ts`

#### Changes Required:

**A. Add Environment Variables & Dependencies**
- Add to package.json: `node-fetch@3.3.2`, `dotenv@16.3.1`
- Load at top of file:
  ```typescript
  import fetch from 'node-fetch';
  import dotenv from 'dotenv';
  dotenv.config();
  
  const INSTANA_BASE_URL = process.env.INSTANA_BASE_URL;
  const INSTANA_API_TOKEN = process.env.INSTANA_API_TOKEN;
  ```

**B. Create Instana API Client Helper**
- Add new function before server creation:
  ```typescript
  async function callInstanaAPI(endpoint: string, params?: any) {
    // Constructs URL: ${INSTANA_BASE_URL}/api${endpoint}
    // Adds header: Authorization: apiToken ${INSTANA_API_TOKEN}
    // Returns parsed JSON or throws error
  }
  ```

**C. Replace `get_stack_traces` Tool (lines 169-193)**

**Current behavior:** Returns hardcoded `STACK_TRACE` constant

**New behavior:**
1. Extract `incidentId` from request arguments
2. Call Instana API: `GET /api/events/{incidentId}`
3. Parse response to extract:
   - `event.snapshot.data` (contains stack trace)
   - `event.text` (error message)
   - `event.triggeredOn` (timestamp)
4. If snapshot exists, call: `GET /api/snapshots/{snapshotId}` for full trace
5. Return actual stack trace with real timestamp
6. If incident not found, return error

**D. Replace `get_service_metrics` Tool (lines 143-167)**

**Current behavior:** Returns hardcoded array `[128, 156, 189, 224, 267, 310, 340]`

**New behavior:**
1. Extract `serviceName` and `windowMinutes` from arguments
2. Calculate time range:
   - `to`: current timestamp
   - `from`: current timestamp - (windowMinutes * 60 * 1000)
3. Call Instana API: `GET /api/application-monitoring/metrics`
   - Query params:
     - `metric`: "memory.used"
     - `service`: serviceName
     - `from`: timestamp
     - `to`: timestamp
     - `rollup`: 60000 (1-minute intervals)
4. Parse response to extract time-series array
5. Calculate growth rate: `(latest - earliest) / windowMinutes`
6. Determine status:
   - "degraded" if growth > 30 MB/min
   - "critical" if growth > 50 MB/min
   - "healthy" otherwise
7. Return actual metrics with real timestamps

**E. Replace `get_active_incidents` Tool (lines 131-141)**

**Current behavior:** Returns hardcoded `ACTIVE_INCIDENT` object

**New behavior:**
1. Call Instana API: `GET /api/events`
   - Query params:
     - `state`: "open"
     - `eventType`: "incident"
     - `windowSize`: 3600000 (last hour)
2. Parse response array
3. Filter for HIGH/CRITICAL severity only
4. Map each incident to our format:
   ```typescript
   {
     id: event.id,
     service: event.service,
     severity: event.severity,
     type: mapEventType(event.eventType),
     startTime: event.start,
     message: event.text,
     snapshotId: event.snapshotId
   }
   ```
5. Return array of real active incidents

**F. Add Error Handling**
- Wrap all API calls in try-catch
- Return structured errors:
  ```typescript
  {
    error: "Instana API unreachable",
    details: error.message,
    timestamp: new Date().toISOString()
  }
  ```
- Log errors to stderr (doesn't interfere with stdio protocol)

---

## 2. FASTAPI WEBHOOK HANDLER CHANGES

### File: `backend/main.py`

#### A. Update Pydantic Model (lines 46-50)

**Current model:**
```python
class IncidentWebhook(BaseModel):
    service: str
    severity: str
    type: str
    incidentId: str
```

**New model:**
```python
class IncidentWebhook(BaseModel):
    incidentId: str
    service: str
    severity: str
    type: str
    snapshotId: Optional[str] = None
    timestamp: str  # ISO 8601 format
    message: str
    eventId: Optional[str] = None
    triggerId: Optional[str] = None
    tags: Optional[Dict[str, str]] = {}
```

#### B. Create MCP Client Module

**New file:** `backend/mcp_client.py`

Purpose: Python client to call MCP server tools

Functions to implement:
```python
async def call_mcp_tool(tool_name: str, args: dict) -> dict:
    """
    Calls MCP server via subprocess
    1. Construct JSON-RPC request
    2. Execute: node mcp-server/build/index.js
    3. Send request via stdin
    4. Read response from stdout
    5. Parse and return JSON
    """

async def get_stack_traces(incident_id: str) -> dict:
    """Wrapper for get_stack_traces tool"""
    
async def get_service_metrics(service: str, window_minutes: int) -> dict:
    """Wrapper for get_service_metrics tool"""
    
async def get_active_incidents() -> list:
    """Wrapper for get_active_incidents tool"""
```

#### C. Rewrite `/webhook` Endpoint (lines 66-95)

**Current behavior:** Stores incident, logs basic info

**New behavior:**
```python
@app.post("/webhook")
async def receive_webhook(incident: IncidentWebhook):
    1. Parse Instana webhook payload
    2. Store in active_incidents with status="received"
    3. Log detailed webhook data:
       - Incident ID
       - Service name
       - Severity
       - Type
       - Timestamp
       - Snapshot ID
    4. Trigger background task: enrich_incident_data(incident.incidentId)
    5. Return 200 OK immediately (don't block webhook)
```

#### D. Create Enrichment Function

**New function in main.py:**
```python
async def enrich_incident_data(incident_id: str):
    """
    Enriches incident with real-time data from MCP server
    Updates active_incidents[incident_id] in place
    """
    1. Get incident from active_incidents
    2. Call MCP: stack_traces = await get_stack_traces(incident_id)
    3. Call MCP: metrics = await get_service_metrics(
         service=incident.service,
         window_minutes=10
       )
    4. Parse stack trace to extract:
       - File path
       - Line number
       - Function name
    5. Update incident record:
       incident['stackTrace'] = stack_traces['stackTrace']
       incident['metrics'] = metrics['memoryMB']
       incident['timestamps'] = metrics['timestamps']
       incident['memoryBefore'] = metrics['memoryMB'][-1]
       incident['growthRate'] = calculate_growth_rate(metrics)
       incident['affectedFile'] = extract_file_from_trace(stack_traces)
       incident['affectedLine'] = extract_line_from_trace(stack_traces)
       incident['status'] = 'enriched'
    6. Log enrichment completion
```

#### E. Create Source Code Reader

**New function in main.py:**
```python
async def read_service_source_code(service_name: str, file_path: str) -> str:
    """
    Reads actual source code from repository
    """
    1. Map service name to repo path:
       SERVICE_PATHS = {
         "payments-api": "./demo-service",
         "orders-api": "./orders-service"
       }
    2. Construct full path: {repo_path}/{file_path}
    3. Read file with error handling
    4. Return file contents or error message
```

#### F. Rewrite `/stream/{incidentId}` Endpoint (lines 99-157)

**Current behavior:** Reads hardcoded file, uses static context

**New behavior:**
```python
@app.get("/stream/{incidentId}")
async def stream_analysis(incidentId: str):
    1. Check if incident exists
    2. Wait for incident status == 'enriched' (max 10 seconds)
    3. If not enriched, return error
    
    4. Build dynamic Bob context:
       a. Get incident data
       b. Read source code:
          - Extract file path from stack trace
          - Read actual file: await read_service_source_code(
              service=incident.service,
              file_path=incident.affectedFile
            )
       c. Format context string:
          """
          INCIDENT DETAILS:
          Service: {incident.service}
          Severity: {incident.severity}
          Type: {incident.type}
          Started: {incident.timestamp}
          
          RUNTIME METRICS:
          Current Memory: {incident.memoryBefore} MB
          Growth Rate: {incident.growthRate} MB/min
          Time Window: {incident.timestamps[0]} to {incident.timestamps[-1]}
          Memory Progression:
          {format_time_series(incident.metrics, incident.timestamps)}
          
          STACK TRACE:
          {incident.stackTrace}
          
          AFFECTED SOURCE CODE:
          File: {incident.affectedFile}
          Line: {incident.affectedLine}
          
          {source_code}
          
          PACKAGE DEPENDENCIES:
          {read package.json if exists}
          """
    
    5. Call call_bob_orchestrator(incident, context_string)
    6. Stream Bob's response via SSE
    7. Store Bob's responses in incident record for deployment
```

---

## 3. CODE ENGINE DEPLOYMENT CHANGES

### File: `backend/bobshell.py`

#### A. Add New Dependencies

Add to `requirements.txt`:
```
docker==7.0.0
ibm-cloud-sdk-core==3.16.0
```

#### B. Create Diff Parser

**New function:**
```python
def parse_bob_diff(code_response: str) -> Dict[str, Any]:
    """
    Parses Bob's CODE phase response to extract structured diff
    """
    1. Use regex to find diff blocks:
       - Pattern: ```diff ... ```
       - Or: --- a/file ... +++ b/file
    2. Extract file path from diff header
    3. Parse hunks: @@ -start,count +start,count @@
    4. Separate additions (+lines) and deletions (-lines)
    5. Return structured object:
       {
         'file': 'server.js',
         'hunks': [
           {
             'old_start': 76,
             'old_count': 1,
             'new_start': 76,
             'new_count': 5,
             'lines': [
               {'type': 'context', 'content': '  sessionCache.set(...)'},
               {'type': 'add', 'content': '  if (sessionCache.size > 100) {'},
               {'type': 'add', 'content': '    sessionCache.clear();'},
               {'type': 'add', 'content': '  }'}
             ]
           }
         ]
       }
```

#### C. Create Diff Applier

**New function:**
```python
def apply_diff_to_file(file_path: str, diff: Dict[str, Any]) -> bool:
    """
    Applies parsed diff to actual file
    """
    1. Read current file content
    2. Split into lines
    3. For each hunk in diff:
       a. Find start line
       b. Remove old_count lines
       c. Insert new lines
    4. Write modified content back to file
    5. Return True if successful, False otherwise
```

#### D. Rewrite `apply_fix_and_deploy()` (lines 23-159)

**Current behavior:** Uses hardcoded fix, simulates deployment

**New behavior:**

**Step 1: Apply Bob's Actual Fix**
```python
1. Get incident from active_incidents
2. Extract Bob's code response from incident['analysis']['code']
3. Parse diff: diff_obj = parse_bob_diff(code_response)
4. Get file path from diff
5. Construct full path: {service_repo_path}/{diff_obj['file']}
6. Apply diff: success = apply_diff_to_file(full_path, diff_obj)
7. If not success:
   - Log error
   - Emit deployment_failed event
   - Return
8. Log: "✓ Applied patch to {file}"
```

**Step 2: Run Real Test Suite**
```python
1. Change directory to service repo
2. Check if package.json has test script
3. Run: subprocess.run(['npm', 'test'], capture_output=True)
4. Stream stdout line by line as log events
5. Check exit code:
   - If 0: Log "✓ All tests passed"
   - If != 0:
     - Log test failures
     - Rollback file changes (git checkout or restore backup)
     - Emit deployment_failed event
     - Return
```

**Step 3: Build Real Docker Image**
```python
1. Generate unique tag:
   tag = f"{service}-{incident_id}-{int(time.time())}"
2. Use Docker SDK:
   import docker
   client = docker.from_env()
   image, logs = client.images.build(
     path="./demo-service",
     tag=tag,
     rm=True
   )
3. Stream build logs:
   for log in logs:
     if 'stream' in log:
       yield _log_event(log['stream'].strip())
4. If build fails:
   - Log error
   - Rollback changes
   - Emit deployment_failed event
   - Return
5. Log: "✓ Image built: {tag}"
```

**Step 4: Push to IBM Container Registry**
```python
1. Get ICR credentials from environment:
   ICR_REGISTRY = os.getenv("ICR_REGISTRY")  # us.icr.io
   ICR_NAMESPACE = os.getenv("ICR_NAMESPACE")
   IBM_CLOUD_API_KEY = os.getenv("IBM_CLOUD_API_KEY")
2. Login to ICR:
   client.login(
     username='iamapikey',
     password=IBM_CLOUD_API_KEY,
     registry=ICR_REGISTRY
   )
3. Tag for ICR:
   full_tag = f"{ICR_REGISTRY}/{ICR_NAMESPACE}/{service}:{tag}"
   image.tag(full_tag)
4. Push image:
   for log in client.images.push(full_tag, stream=True, decode=True):
     if 'status' in log:
       yield _log_event(f"  {log['status']}")
5. Log: "✓ Image pushed: {full_tag}"
```

**Step 5: Deploy to Code Engine**
```python
1. Get Code Engine config from environment:
   CE_PROJECT = os.getenv("CODE_ENGINE_PROJECT")
   CE_APP = os.getenv("CODE_ENGINE_APP")
   IBM_CLOUD_REGION = os.getenv("IBM_CLOUD_REGION")
2. Use IBM Cloud CLI or REST API:
   Option A - CLI:
   subprocess.run([
     'ibmcloud', 'ce', 'app', 'update',
     CE_APP,
     '--image', full_tag,
     '--wait'
   ])
   
   Option B - REST API:
   from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
   authenticator = IAMAuthenticator(IBM_CLOUD_API_KEY)
   # Call Code Engine API to update app
3. Parse output to get new revision name
4. Log: "✓ New revision created: {revision_name}"
```

**Step 6: Health Check & Verification**
```python
1. Get app URL from Code Engine:
   - CLI: ibmcloud ce app get {CE_APP} --output json
   - Parse JSON to extract URL
2. Construct health endpoint: {app_url}/health
3. Poll health endpoint:
   max_attempts = 30
   interval = 2  # seconds
   for attempt in range(max_attempts):
     try:
       response = requests.get(health_url, timeout=5)
       if response.status_code == 200:
         health_data = response.json()
         memory_mb = parse_memory(health_data['memory']['heapUsed'])
         cache_size = health_data['cacheSize']
         
         # Check if healthy
         if memory_mb < 200 and cache_size < 150:
           # SUCCESS
           break
     except:
       pass
     await asyncio.sleep(interval)
4. If healthy:
   a. Query /health to get actual memoryAfter
   b. Calculate actual MTTR:
      start = datetime.fromisoformat(incident['timestamp'])
      end = datetime.now()
      mttr_seconds = (end - start).total_seconds()
      mttr_formatted = format_mttr(mttr_seconds)
   c. Emit completion event:
      {
        "type": "completion",
        "status": "resolved",
        "incidentId": incident_id,
        "resolvedAt": datetime.now().isoformat(),
        "revision": revision_name,
        "memoryBefore": f"{incident['memoryBefore']}MB",
        "memoryAfter": f"{memory_mb}MB",
        "mttr": mttr_formatted
      }
5. If unhealthy after 60 seconds:
   a. Log: "⚠️ Health check failed"
   b. Trigger rollback
   c. Emit deployment_failed event
```

#### E. Add Rollback Function

**New function:**
```python
async def rollback_deployment(incident_id: str, reason: str):
    """
    Rolls back to previous Code Engine revision
    """
    1. Get previous revision:
       - CLI: ibmcloud ce app get {CE_APP} --output json
       - Parse to find previous revision name
    2. Update app to previous revision:
       subprocess.run([
         'ibmcloud', 'ce', 'app', 'update',
         CE_APP,
         '--revision', previous_revision,
         '--wait'
       ])
    3. Verify rollback health
    4. Log: "✓ Rolled back to {previous_revision}"
    5. Emit rollback event
```

#### F. Add Helper Functions

**New functions:**
```python
def format_mttr(seconds: float) -> str:
    """Formats MTTR as 'X minutes Y seconds'"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes} minutes {secs} seconds"

def parse_memory(memory_string: str) -> int:
    """Parses '340MB' to 340"""
    return int(memory_string.replace('MB', '').strip())

def calculate_growth_rate(metrics: list, timestamps: list) -> float:
    """Calculates MB/min growth rate"""
    if len(metrics) < 2:
        return 0.0
    time_diff_minutes = (
        datetime.fromisoformat(timestamps[-1]) - 
        datetime.fromisoformat(timestamps[0])
    ).total_seconds() / 60
    memory_diff = metrics[-1] - metrics[0]
    return memory_diff / time_diff_minutes if time_diff_minutes > 0 else 0.0
```

---

## 4. ENVIRONMENT CONFIGURATION

### File: `.env.example`

Create/update with all required variables:

```bash
# ===== IBM Bob API =====
BOB_API_KEY=your_bob_api_key_here
BOB_API_URL=https://api.bob.ibm.com/v1/generate

# ===== Instana Monitoring =====
INSTANA_BASE_URL=https://your-tenant.instana.io
INSTANA_API_TOKEN=your_instana_api_token_here
# Get token from: Instana UI → Settings → API Tokens

# ===== IBM Cloud Authentication =====
IBM_CLOUD_API_KEY=your_ibm_cloud_api_key_here
# Create at: https://cloud.ibm.com/iam/apikeys
IBM_CLOUD_REGION=us-south
# Options: us-south, us-east, eu-de, eu-gb, jp-tok, jp-osa, au-syd, ca-tor, br-sao

# ===== IBM Container Registry =====
ICR_REGISTRY=us.icr.io
# Must match region: us.icr.io, eu.icr.io, jp.icr.io, au.icr.io, uk.icr.io
ICR_NAMESPACE=opsbob-demo
# Create namespace: ibmcloud cr namespace-add opsbob-demo

# ===== IBM Code Engine =====
CODE_ENGINE_PROJECT=opsbob-demo
# Create project: ibmcloud ce project create --name opsbob-demo
CODE_ENGINE_APP=payments-api
# The application name in Code Engine to update

# ===== Service Configuration =====
DEMO_SERVICE_PORT=3000
DEMO_SERVICE_PATH=./demo-service
# Path to the service repository being monitored

# ===== Backend Configuration =====
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3001
# For CORS configuration

# ===== Deployment Settings =====
HEALTH_CHECK_TIMEOUT=60
# Maximum seconds to wait for health check after deployment
HEALTH_CHECK_INTERVAL=2
# Seconds between health check polling attempts
MEMORY_THRESHOLD_MB=300
# Memory threshold for alerting (MB)
CACHE_SIZE_THRESHOLD=1000
# Cache size threshold for alerting

# ===== MCP Server Configuration =====
MCP_SERVER_PATH=./mcp-server/build/index.js
# Path to compiled MCP server
```

### File: `backend/config.py` (new file)

Create configuration module:

```python
"""
Configuration for OpsBob Backend
Maps services to repositories and defines thresholds
"""
import os

# Service to repository path mapping
SERVICE_REPO_MAP = {
    "payments-api": "./demo-service",
    "orders-api": "./orders-service",
    "inventory-api": "./inventory-service",
}

# Service to main file mapping
SERVICE_MAIN_FILE = {
    "payments-api": "server.js",
    "orders-api": "app.js",
    "inventory-api": "index.js",
}

# Instana event type to our incident type mapping
INSTANA_EVENT_TYPE_MAP = {
    "memory": "MEMORY_LEAK",
    "cpu": "CPU_SPIKE",
    "error_rate": "ERROR_RATE_HIGH",
    "latency": "HIGH_LATENCY",
    "availability": "SERVICE_DOWN",
}

# Health check thresholds
MEMORY_THRESHOLD_MB = int(os.getenv("MEMORY_THRESHOLD_MB", "300"))
CACHE_SIZE_THRESHOLD = int(os.getenv("CACHE_SIZE_THRESHOLD", "1000"))
HEALTH_CHECK_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "60"))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "2"))
```

---

## 5. ADDITIONAL FILES TO MODIFY

### A. `backend/requirements.txt`

Add new dependencies:
```
# Existing
aiohttp==3.9.1
python-dotenv==1.0.0
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0

# New additions
docker==7.0.0              # Docker SDK for Python
ibm-cloud-sdk-core==3.16.0 # IBM Cloud SDK
requests==2.31.0           # Synchronous HTTP requests
python-dateutil==2.8.2     # Date parsing and formatting
```

### B. `mcp-server/package.json`

Add new dependencies:
```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^0.5.0",
    "node-fetch": "^3.3.2",
    "dotenv": "^16.3.1"
  }
}
```

### C. `mcp-server/tsconfig.json`

Ensure proper configuration:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ES2020",
    "moduleResolution": "node",
    "esModuleInterop": true,
    "outDir": "./build"
  }
}
```

---

## 6. IMPLEMENTATION SEQUENCE

### Phase 1: MCP Server (Week 1)
1. Add Instana API client to MCP server
2. Replace get_stack_traces with real API call
3. Replace get_service_metrics with real API call
4. Replace get_active_incidents with real API call
5. Test MCP server independently with real Instana data

### Phase 2: Backend Integration (Week 2)
1. Create mcp_client.py module
2. Update IncidentWebhook model
3. Implement enrich_incident_data()
4. Update /webhook endpoint
5. Update /stream endpoint with dynamic context
6. Test end-to-end: webhook → enrichment → Bob analysis

### Phase 3: Deployment Automation (Week 3)
1. Implement parse_bob_diff()
2. Implement apply_diff_to_file()
3. Update apply_fix_and_deploy() with real Docker operations
4. Implement Code Engine deployment
5. Implement health check polling
6. Implement rollback functionality
7. Test full deployment pipeline

### Phase 4: Testing & Validation (Week 4)
1. Integration testing with real Instana webhooks
2. Verify Bob receives correct context
3. Verify deployments work end-to-end
4. Verify MTTR calculations are accurate
5. Load testing and error handling
6. Documentation updates

---

## 7. TESTING STRATEGY

### Unit Tests

**File: `backend/test_mcp_client.py`**
- Test MCP tool calls
- Mock MCP server responses
- Test error handling

**File: `backend/test_bobshell.py`**
- Test parse_bob_diff()
- Test apply_diff_to_file()
- Test format_mttr()
- Test calculate_growth_rate()

**File: `mcp-server/test/instana-client.test.ts`**
- Test Instana API calls
- Mock Instana responses
- Test error handling

### Integration Tests

**File: `backend/test_integration.py`**
- Test webhook → enrichment flow
- Test enrichment → Bob analysis flow
- Test Bob analysis → deployment flow
- Test health check polling
- Test rollback scenarios

### Manual Testing Checklist

- [ ] Trigger real Instana alert
- [ ] Verify webhook received correctly
- [ ] Verify MCP server queries Instana
- [ ] Verify stack trace is real
- [ ] Verify metrics are live time-series
- [ ] Verify Bob receives correct context
- [ ] Verify Bob's fix is parsed correctly
- [ ] Verify diff is applied to file
- [ ] Verify tests run
- [ ] Verify Docker image builds
- [ ] Verify image pushes to ICR
- [ ] Verify Code Engine deployment
- [ ] Verify health check passes
- [ ] Verify MTTR is calculated correctly
- [ ] Verify memory before/after are real values
- [ ] Test rollback on failed health check

---

## 8. ROLLOUT PLAN

### Development Environment
1. Set up test Instana tenant
2. Create test Code Engine project
3. Configure all environment variables
4. Deploy demo service to Code Engine
5. Test with synthetic incidents

### Staging Environment
1. Use production Instana (read-only)
2. Deploy to staging Code Engine project
3. Test with real incidents (manual approval only)
4. Validate all metrics and deployments

### Production Environment
1. Enable production Instana webhooks
2. Deploy to production Code Engine
3. Monitor first 10 incidents closely
4. Gradually increase automation confidence
5. Enable auto-approval for low-risk fixes

---

## 9. SUCCESS CRITERIA

### Functional Requirements
- ✅ Instana webhook triggers real-time enrichment
- ✅ MCP server returns live stack traces
- ✅ MCP server returns live metrics
- ✅ Bob receives dynamic context (no hardcoded data)
- ✅ Bob's fix is parsed and applied correctly
- ✅ Docker image builds successfully
- ✅ Image pushes to ICR
- ✅ Code Engine deployment succeeds
- ✅ Health check validates fix
- ✅ MTTR is calculated from real timestamps
- ✅ Memory before/after are queried from service

### Performance Requirements
- Webhook processing: < 2 seconds
- Enrichment: < 5 seconds
- Bob analysis: < 30 seconds
- Deployment: < 3 minutes
- Total MTTR: < 5 minutes

### Reliability Requirements
- Handle Instana API failures gracefully
- Rollback on failed health checks
- Retry failed deployments
- Log all errors for debugging
- Alert on system failures

---

## 10. RISKS & MITIGATION

### Risk: Instana API Rate Limiting
**Mitigation:** 
- Cache metrics for 1 minute
- Implement exponential backoff
- Use batch API calls where possible

### Risk: Docker Build Failures
**Mitigation:**
- Validate Dockerfile before build
- Use multi-stage builds for faster iterations
- Keep base images cached

### Risk: Code Engine Deployment Failures
**Mitigation:**
- Implement automatic rollback
- Keep previous revision available
- Monitor deployment status closely

### Risk: Bob Generates Invalid Fix
**Mitigation:**
- Run tests before deployment
- Syntax check before applying diff
- Human approval required for production

### Risk: Health Check False Negatives
**Mitigation:**
- Multiple health check attempts
- Configurable thresholds
- Manual override capability

---

**Plan Complete - Ready for Implementation**

This plan transforms OpsBob into a production-ready system that uses real data at every step, from incident detection through deployment verification.