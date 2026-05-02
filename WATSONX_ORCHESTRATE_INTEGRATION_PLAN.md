# watsonx Orchestrate Integration Plan for OpsBob

## Overview
This plan details the integration of watsonx Orchestrate as the approval and escalation layer for OpsBob. Instead of manual approval via the React dashboard, Bob will notify Orchestrate with a Fix Card, which routes to the appropriate approver who responds in plain English.

---

## 1. NEW ENDPOINT: POST /orchestrate/decision

### Location in main.py
**Insert after line 294** (after the existing `/approve/{incidentId}` endpoint)

### Specification

```python
class OrchestrateDecision(BaseModel):
    incident_id: str
    action: str  # "approve" | "escalate" | "reject"
    approver: str  # Name or ID of the person who made the decision
    reason: str  # Natural language explanation

@app.post("/orchestrate/decision")
async def receive_orchestrate_decision(decision: OrchestrateDecision):
    """
    Receives approval/rejection/escalation decisions from watsonx Orchestrate
    
    This endpoint is called by Orchestrate after a human approver responds.
    It replaces the manual approval button flow.
    """
```

### Logic Flow
1. **Validate incident exists** - Check `active_incidents[decision.incident_id]`
2. **Route based on action:**
   - **"approve"**: 
     - Set `incident["status"] = "deploying"`
     - Set `incident["approver"] = decision.approver`
     - Set `incident["approval_reason"] = decision.reason`
     - Return deployment stream URL
   - **"escalate"**:
     - Set `incident["status"] = "escalated"`
     - Set `incident["escalated_to"] = decision.approver`
     - Set `incident["escalation_reason"] = decision.reason`
     - Log to audit trail (no deployment)
   - **"reject"**:
     - Set `incident["status"] = "rejected"`
     - Set `incident["rejected_by"] = decision.approver`
     - Set `incident["rejection_reason"] = decision.reason`
     - Log to audit trail (no deployment)

### Response Format
```json
{
  "status": "deploying" | "escalated" | "rejected",
  "incidentId": "string",
  "message": "Human-readable status message",
  "approver": "string"
}
```

---

## 2. NEW FUNCTION: notify_orchestrate()

### Location in main.py
**Insert after line 241** (immediately after Bob's streaming completes in `event_generator()`)

### Function Signature
```python
async def notify_orchestrate(
    incident_id: str,
    service_name: str,
    fix_summary: str,
    confidence: str,
    bob_response: str
) -> bool:
    """
    Sends Fix Card to watsonx Orchestrate for human approval
    
    Returns True if notification succeeded, False otherwise
    """
```

### Implementation Details

**Environment Variables Required:**
- `ORCHESTRATE_BASE_URL` - Base URL for Orchestrate API
- `ORCHESTRATE_API_TOKEN` - Bearer token for authentication

**Fix Card Payload:**
```json
{
  "incident_id": "string",
  "service_name": "string",
  "fix_summary": "string (extracted from Bob's plan phase)",
  "confidence": "high" | "medium" | "low",
  "bob_full_response": "string (complete code fix)",
  "dashboard_url": "http://localhost:3000/incident/{incident_id}",
  "callback_url": "http://localhost:8000/orchestrate/decision",
  "timestamp": "ISO 8601 timestamp"
}
```

**HTTP Request:**
- Method: POST
- Endpoint: `{ORCHESTRATE_BASE_URL}/api/v1/fix-cards`
- Headers:
  - `Authorization: Bearer {ORCHESTRATE_API_TOKEN}`
  - `Content-Type: application/json`
- Timeout: 10 seconds

**Error Handling:**
- Log failures but don't block the stream
- Store notification status in `incident["orchestrate_notified"]`
- If notification fails, fall back to dashboard approval

### Integration Point in event_generator()

**Current code (lines 231-241):**
```python
async for event in call_bob_orchestrator(context):
    event_data = json.loads(event.replace("data: ", "").strip())
    
    if event_data.get("phase") == "code" and event_data.get("done"):
        incident["bob_response"] = event_data.get("content", "")
    
    yield event

print(f"Completed streaming analysis for {incidentId}")
```

**Modified code:**
```python
# Track phases for metadata extraction
plan_response = ""
code_response = ""

async for event in call_bob_orchestrator(context):
    event_data = json.loads(event.replace("data: ", "").strip())
    
    # Store plan phase for confidence scoring
    if event_data.get("phase") == "plan" and event_data.get("done"):
        plan_response = event_data.get("content", "")
        incident["bob_plan"] = plan_response
    
    # Store code phase for deployment
    if event_data.get("phase") == "code" and event_data.get("done"):
        code_response = event_data.get("content", "")
        incident["bob_response"] = code_response
    
    yield event

print(f"Completed streaming analysis for {incidentId}")

# After streaming completes, notify Orchestrate
if plan_response and code_response:
    confidence = calculate_confidence(plan_response)
    fix_summary = extract_fix_summary(plan_response)
    
    success = await notify_orchestrate(
        incident_id=incidentId,
        service_name=incident["service"],
        fix_summary=fix_summary,
        confidence=confidence,
        bob_response=code_response
    )
    
    incident["orchestrate_notified"] = success
    if success:
        print(f"Orchestrate notified for incident {incidentId}")
    else:
        print(f"Failed to notify Orchestrate for {incidentId} - falling back to dashboard")
```

---

## 3. CONFIDENCE SCORING FUNCTION

### Location in main.py
**Insert after line 58** (after Pydantic models, before startup event)

### Function Specification

```python
def calculate_confidence(plan_text: str) -> str:
    """
    Analyzes Bob's plan-phase response to determine confidence level
    
    Returns: "high", "medium", or "low"
    
    Logic:
    - HIGH: No uncertainty markers, clear root cause identified
    - MEDIUM: Some uncertainty or multiple possible causes
    - LOW: Significant uncertainty or unable to pinpoint root cause
    """
```

### Uncertainty Markers (case-insensitive)
**Low confidence indicators:**
- "might", "maybe", "possibly", "unclear", "uncertain"
- "could be", "may be", "not sure", "difficult to determine"
- "multiple possible", "several potential"

**Medium confidence indicators:**
- "likely", "probably", "appears to be", "seems to"
- "most likely", "suggests", "indicates"

**High confidence indicators:**
- "definitely", "clearly", "certainly", "identified"
- "root cause is", "the issue is", "caused by"
- No uncertainty markers present

### Algorithm
1. Convert plan_text to lowercase
2. Count uncertainty markers:
   - 0 markers + positive indicators = HIGH
   - 1-2 markers = MEDIUM
   - 3+ markers = LOW
3. Check for explicit confidence statements from Bob
4. Default to MEDIUM if ambiguous

---

## 4. FIX SUMMARY EXTRACTION FUNCTION

### Location in main.py
**Insert after confidence function** (around line 80)

### Function Specification

```python
def extract_fix_summary(plan_text: str) -> str:
    """
    Extracts a concise fix summary from Bob's plan-phase response
    
    Returns: Single sentence summary (max 150 chars)
    
    Logic:
    1. Look for "Root cause:" or "Fix:" sections
    2. Extract first 1-2 sentences
    3. Truncate to 150 characters if needed
    4. Fall back to first sentence if no markers found
    """
```

### Extraction Strategy
1. Search for key phrases:
   - "Root cause:"
   - "The fix:"
   - "Solution:"
   - "To resolve:"
2. Extract text after marker until period or newline
3. Clean up formatting (remove extra whitespace)
4. Truncate to 150 chars with "..." if needed
5. Default: Return first sentence of plan_text

---

## 5. ENVIRONMENT VARIABLES

### Location: .env.example
**Insert after line 58** (after SOURCE_FILES_PATH section)

### New Section

```bash
# ============================================================================
# watsonx Orchestrate Configuration
# ============================================================================
# watsonx Orchestrate base URL for Fix Card notifications
# Example: https://orchestrate.ibm.com
ORCHESTRATE_BASE_URL=https://your-orchestrate-instance.ibm.com

# watsonx Orchestrate API token for authentication
# Generate from: Orchestrate UI → Settings → API Tokens
ORCHESTRATE_API_TOKEN=your_orchestrate_api_token_here
```

### Also add to main.py imports section (after line 29)

```python
ORCHESTRATE_BASE_URL = os.getenv("ORCHESTRATE_BASE_URL")
ORCHESTRATE_API_TOKEN = os.getenv("ORCHESTRATE_API_TOKEN")
```

---

## 6. EXACT LINE CHANGES IN main.py

### Section A: Imports (no changes needed)
Lines 1-29 remain unchanged

### Section B: Environment Variables
**After line 29, add:**
```python
ORCHESTRATE_BASE_URL = os.getenv("ORCHESTRATE_BASE_URL")
ORCHESTRATE_API_TOKEN = os.getenv("ORCHESTRATE_API_TOKEN")
```

### Section C: Pydantic Models
**After line 58 (after ApprovalRequest), add:**
```python
class OrchestrateDecision(BaseModel):
    incident_id: str
    action: str  # "approve" | "escalate" | "reject"
    approver: str
    reason: str
```

### Section D: Helper Functions
**After line 58 (after Pydantic models), add:**
```python
def calculate_confidence(plan_text: str) -> str:
    """Calculate confidence level from Bob's plan response"""
    # Implementation as specified above

def extract_fix_summary(plan_text: str) -> str:
    """Extract concise fix summary from Bob's plan"""
    # Implementation as specified above

async def notify_orchestrate(
    incident_id: str,
    service_name: str,
    fix_summary: str,
    confidence: str,
    bob_response: str
) -> bool:
    """Send Fix Card to watsonx Orchestrate"""
    # Implementation as specified above
```

### Section E: Stream Analysis Endpoint Modification
**Lines 231-241 (inside event_generator) - REPLACE with:**
```python
# Track phases for metadata extraction
plan_response = ""
code_response = ""

async for event in call_bob_orchestrator(context):
    event_data = json.loads(event.replace("data: ", "").strip())
    
    # Store plan phase for confidence scoring
    if event_data.get("phase") == "plan" and event_data.get("done"):
        plan_response = event_data.get("content", "")
        incident["bob_plan"] = plan_response
    
    # Store code phase for deployment
    if event_data.get("phase") == "code" and event_data.get("done"):
        code_response = event_data.get("content", "")
        incident["bob_response"] = code_response
    
    yield event

print(f"Completed streaming analysis for {incidentId}")

# After streaming completes, notify Orchestrate
if plan_response and code_response:
    confidence = calculate_confidence(plan_response)
    fix_summary = extract_fix_summary(plan_response)
    
    success = await notify_orchestrate(
        incident_id=incidentId,
        service_name=incident["service"],
        fix_summary=fix_summary,
        confidence=confidence,
        bob_response=code_response
    )
    
    incident["orchestrate_notified"] = success
    if success:
        print(f"Orchestrate notified for incident {incidentId}")
    else:
        print(f"Failed to notify Orchestrate for {incidentId}")
```

### Section F: New Orchestrate Decision Endpoint
**After line 294 (after /approve endpoint), add:**
```python
@app.post("/orchestrate/decision")
async def receive_orchestrate_decision(decision: OrchestrateDecision):
    """
    Receives approval/rejection/escalation from watsonx Orchestrate
    """
    # Implementation as specified above
```

---

## 7. BACKWARD COMPATIBILITY

The existing `/approve/{incidentId}` endpoint (lines 264-294) remains unchanged for:
- Direct dashboard approvals (fallback if Orchestrate fails)
- Testing and development
- Manual override capability

---

## 8. DEPLOYMENT FLOW COMPARISON

### Current Flow
```
Webhook → Bob Analysis → Dashboard Display → Manual Approve Button → Deployment
```

### New Flow with Orchestrate
```
Webhook → Bob Analysis → notify_orchestrate() → Orchestrate Routes to Approver →
Approver Responds (plain English) → /orchestrate/decision → Deployment
```

### Fallback Flow (if Orchestrate unavailable)
```
Webhook → Bob Analysis → notify_orchestrate() fails → Dashboard Approve Button → Deployment
```

---

## 9. TESTING STRATEGY

1. **Unit Tests:**
   - `calculate_confidence()` with various plan texts
   - `extract_fix_summary()` with different formats
   - `notify_orchestrate()` with mock HTTP responses

2. **Integration Tests:**
   - Full flow with mock Orchestrate API
   - Fallback behavior when Orchestrate is down
   - All three decision types (approve/escalate/reject)

3. **Manual Testing:**
   - Real Orchestrate integration
   - Natural language approval parsing
   - Dashboard still works as fallback

---

## 10. SECURITY CONSIDERATIONS

1. **API Token Storage:**
   - Store `ORCHESTRATE_API_TOKEN` in .env (never commit)
   - Use environment variables only
   - Rotate tokens regularly

2. **Endpoint Authentication:**
   - `/orchestrate/decision` should validate incoming requests
   - Consider adding HMAC signature verification
   - Rate limiting to prevent abuse

3. **Data Privacy:**
   - Fix Cards may contain sensitive code
   - Ensure Orchestrate connection uses HTTPS
   - Log decisions but sanitize sensitive data

---

## 11. ROLLOUT PLAN

### Phase 1: Development (Week 1)
- Implement all four changes
- Add unit tests
- Test with mock Orchestrate API

### Phase 2: Staging (Week 2)
- Deploy to staging environment
- Connect to real Orchestrate instance
- Test with sample incidents

### Phase 3: Production (Week 3)
- Enable for 10% of incidents (feature flag)
- Monitor success rate
- Gradually increase to 100%

### Phase 4: Deprecation (Week 4+)
- Keep dashboard approval as backup
- Monitor usage patterns
- Document lessons learned

---

## Summary of Changes

| File | Lines Changed | Type |
|------|---------------|------|
| `backend/main.py` | 29-30 | Add env vars |
| `backend/main.py` | 58-59 | Add Pydantic model |
| `backend/main.py` | 60-120 | Add helper functions |
| `backend/main.py` | 231-270 | Modify event_generator |
| `backend/main.py` | 295-330 | Add new endpoint |
| `.env.example` | 59-67 | Add Orchestrate config |

**Total new lines:** ~150
**Modified lines:** ~40
**New dependencies:** `aiohttp` (already present)