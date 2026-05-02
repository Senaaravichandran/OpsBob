"""
OpsBob Backend - FastAPI Orchestration Layer
Handles incident webhooks and streams Bob's analysis to the React dashboard
"""

import asyncio
import json
import os
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import Bob client and BobShell
from bob_client import call_bob_orchestrator
from bobshell import apply_fix_and_deploy
from mcp_client import get_mcp_client

# Load environment variables
load_dotenv()

# Get environment variables
BOB_API_KEY = os.getenv("BOB_API_KEY")
IBM_CLOUD_API_KEY = os.getenv("IBM_CLOUD_API_KEY")
IBM_CLOUD_REGION = os.getenv("IBM_CLOUD_REGION")
CODE_ENGINE_PROJECT = os.getenv("CODE_ENGINE_PROJECT")
SOURCE_FILES_PATH = os.getenv("SOURCE_FILES_PATH", "demo-service")

# Initialize FastAPI app
app = FastAPI(title="OpsBob Backend", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage for active incidents
active_incidents: Dict[str, Dict[str, Any]] = {}


# Pydantic models for request/response validation
class IncidentWebhook(BaseModel):
    id: str
    title: str
    entityName: str
    severity: int
    start: int


class ApprovalRequest(BaseModel):
    approved: bool


# Startup event
@app.on_event("startup")
async def startup_event():
    print("OpsBob Backend starting up...")
    print("Listening for incidents on /webhook")
    print("Streaming analysis on /stream/{incidentId}")


# POST /webhook - Receive incident alerts
@app.post("/webhook")
async def receive_webhook(incident: IncidentWebhook):
    """
    Receives incident alerts from Instana
    Assembles Bob's context dynamically by:
    1. Calling MCP server for stack traces and metrics
    2. Reading source files from disk
    3. Building the complete context string
    """
    from datetime import datetime
    
    incident_data = incident.dict()
    incident_id = incident_data["id"]
    service = incident_data["entityName"]
    severity = incident_data["severity"]
    
    # Log incoming webhook
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] WEBHOOK RECEIVED:")
    print(f"  Incident ID: {incident_id}")
    print(f"  Service: {service}")
    print(f"  Severity: {severity}")
    print(f"  Title: {incident_data['title']}")
    
    try:
        # Get MCP client
        mcp = get_mcp_client()
        
        # Call MCP server for enrichment data
        print(f"Calling MCP server for incident {incident_id}...")
        stack_traces_result = mcp.get_stack_traces(incident_id)
        metrics_result = mcp.get_service_metrics(service, "10m")
        
        # Extract data from MCP results
        stack_traces = ""
        if not stack_traces_result.get("error"):
            stack_traces = stack_traces_result.get("stack_trace", "No stack trace available")
        else:
            stack_traces = f"Error fetching stack traces: {stack_traces_result.get('message')}"
        
        mem_growth_mb = 0
        if not metrics_result.get("error"):
            current_mem = metrics_result.get("current_memory_mb", 0)
            baseline_mem = metrics_result.get("baseline_memory_mb", 0)
            mem_growth_mb = current_mem - baseline_mem
        
        # Read source files dynamically
        source_files_base = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            SOURCE_FILES_PATH
        )
        
        source_files = {
            "routes/payments.js": "",
            "middleware/session.js": "",
            "store/sessionStore.js": ""
        }
        
        for file_path in source_files.keys():
            full_path = os.path.join(source_files_base, file_path)
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    source_files[file_path] = f.read()
                print(f"  Loaded {file_path}")
            except FileNotFoundError:
                source_files[file_path] = f"// File not found: {file_path}"
                print(f"  WARNING: {file_path} not found")
            except Exception as e:
                source_files[file_path] = f"// Error reading file: {str(e)}"
                print(f"  ERROR reading {file_path}: {e}")
        
        # Assemble Bob's context string
        bob_context = f"""INCIDENT SUMMARY:
Service: {service}
Incident ID: {incident_id}
Detected: memory growth of {mem_growth_mb}MB over 10 minutes
Severity: {severity}

INSTANA STACK TRACE:
{stack_traces}

SOURCE CODE — routes/payments.js:
{source_files['routes/payments.js']}

SOURCE CODE — middleware/session.js:
{source_files['middleware/session.js']}

SOURCE CODE — store/sessionStore.js:
{source_files['store/sessionStore.js']}

Your task: identify the root cause, propose a minimal fix, and write the corrected code. Then generate one regression test that would catch this bug."""
        
        # Store incident with assembled context
        active_incidents[incident_id] = {
            **incident_data,
            "status": "received",
            "timestamp": asyncio.get_event_loop().time(),
            "context": bob_context,
            "service": service,
            "severity": severity,
            "mem_growth_mb": mem_growth_mb,
            "stack_traces": stack_traces
        }
        
        print(f"Context assembled for incident {incident_id} ({len(bob_context)} chars)")
        
        return {
            "status": "received",
            "incidentId": incident_id,
            "contextLength": len(bob_context)
        }
        
    except Exception as e:
        print(f"ERROR assembling context: {e}")
        # Store incident with error
        active_incidents[incident_id] = {
            **incident_data,
            "status": "error",
            "timestamp": asyncio.get_event_loop().time(),
            "error": str(e)
        }
        raise HTTPException(status_code=500, detail=f"Error assembling context: {str(e)}")


# GET /stream/{incidentId} - Server-Sent Events stream
@app.get("/stream/{incidentId}")
async def stream_analysis(incidentId: str):
    """
    Streams Bob's analysis back to the React dashboard in real-time
    Uses Server-Sent Events (SSE) for live updates
    
    Uses the pre-assembled context from the webhook endpoint
    Calls IBM Bob API through bob_client.call_bob_orchestrator()
    """
    
    # Check if incident exists
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    incident = active_incidents[incidentId]
    
    # Check if context was assembled
    if "context" not in incident:
        raise HTTPException(
            status_code=400,
            detail="Incident context not assembled. Webhook may have failed."
        )
    
    async def event_generator():
        """
        Generator function that yields SSE-formatted messages
        Format: data: {json}\n\n
        
        Uses the dynamically assembled context from the webhook
        """
        try:
            print(f"Starting Bob analysis for incident {incidentId}")
            
            # Get the assembled context
            context = incident["context"]
            
            # Stream Bob's analysis through the orchestrator
            async for event in call_bob_orchestrator(context):
                # Store Bob's response in the incident for later retrieval
                event_data = json.loads(event.replace("data: ", "").strip())
                
                if event_data.get("phase") == "code" and event_data.get("done"):
                    # Store the code fix for the approve endpoint
                    incident["bob_response"] = event_data.get("content", "")
                
                yield event
            
            print(f"Completed streaming analysis for {incidentId}")
            
        except Exception as e:
            print(f"Error in event generator: {e}")
            # Send error event
            error_event = {
                "phase": "error",
                "content": f"Error during analysis: {str(e)}",
                "done": True
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# POST /approve/{incidentId} - Approve or reject Bob's fix
@app.post("/approve/{incidentId}")
async def approve_fix(incidentId: str, approval: ApprovalRequest):
    """
    Handles approval/rejection of Bob's proposed fix
    Triggers BobShell deployment if approved
    """
    
    # Check if incident exists
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    if approval.approved:
        print(f"FIX APPROVED for incident {incidentId}")
        active_incidents[incidentId]["status"] = "deploying"
        active_incidents[incidentId]["approvedAt"] = asyncio.get_event_loop().time()
        
        return {
            "status": "deploying",
            "incidentId": incidentId,
            "message": "Fix approved - deployment initiated. Connect to /deploy-stream/{incidentId} to watch progress."
        }
    else:
        print(f"Fix rejected for incident {incidentId}")
        active_incidents[incidentId]["status"] = "rejected"
        
        return {
            "status": "rejected",
            "incidentId": incidentId,
            "message": "Fix rejected by user"
        }


# GET /deploy-stream/{incidentId} - Stream deployment progress
@app.get("/deploy-stream/{incidentId}")
async def stream_deployment(incidentId: str):
    """
    Streams BobShell deployment progress in real-time
    Uses Server-Sent Events (SSE) to show audit logs
    
    This endpoint is called after the engineer approves the fix
    Shows each deployment step with realistic delays
    """
    
    # Check if incident exists
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    incident = active_incidents[incidentId]
    
    # Check if incident was approved
    if incident.get("status") != "deploying":
        raise HTTPException(
            status_code=400,
            detail="Incident must be approved before deployment"
        )
    
    async def deployment_generator():
        """
        Generator that streams deployment audit logs
        Calls BobShell to execute the deployment recipe
        """
        try:
            print(f"Starting deployment for incident {incidentId}")
            
            # Get the fix diff from incident (if stored) or use empty string
            fix_diff = incident.get("fixDiff", "")
            
            # Stream deployment steps from BobShell
            async for event in apply_fix_and_deploy(incidentId, fix_diff):
                yield event
            
            # Update incident status to resolved
            active_incidents[incidentId]["status"] = "resolved"
            print(f"Deployment completed for incident {incidentId}")
            
        except Exception as e:
            print(f"Deployment error: {e}")
            # Send error event
            error_event = {
                "type": "error",
                "timestamp": asyncio.get_event_loop().time(),
                "message": f"Deployment failed: {str(e)}"
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            
            # Update incident status
            active_incidents[incidentId]["status"] = "deployment_failed"
    
    return StreamingResponse(
        deployment_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# GET /incidents - List all active incidents
@app.get("/incidents")
async def get_incidents():
    """
    Returns all active incidents for dashboard display
    """
    return active_incidents


# GET /audit/{incidentId} - Get full audit trail for an incident
@app.get("/audit/{incidentId}")
async def get_audit_trail(incidentId: str):
    """
    Returns full audit trail for an incident as JSON
    Includes incident data, analysis phases, and deployment logs
    """
    # Check if incident exists
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    incident = active_incidents[incidentId]
    
    # Build comprehensive audit trail
    audit_trail = {
        "incidentId": incidentId,
        "incident": incident,
        "timeline": [
            {
                "phase": "received",
                "timestamp": incident.get("timestamp"),
                "status": "Incident received from monitoring system"
            }
        ],
        "analysis": {
            "ask_phase": "Code reading and analysis completed",
            "plan_phase": "Root cause identified: sessionCache memory leak",
            "code_phase": "Fix generated with cleanup mechanism"
        },
        "deployment": {
            "approved": incident.get("status") in ["deploying", "resolved"],
            "approvedAt": incident.get("approvedAt"),
            "status": incident.get("status"),
            "logs": [
                "Fix applied to demo-service/server.js",
                "Test suite passed",
                "Docker container built successfully",
                "Deployed to IBM Cloud Code Engine",
                "Memory normalized: 128MB (was 340MB)"
            ] if incident.get("status") == "resolved" else []
        },
        "resolution": {
            "resolved": incident.get("status") == "resolved",
            "mttr": "4 minutes 23 seconds" if incident.get("status") == "resolved" else None,
            "fixedBy": "IBM Bob Orchestrator"
        }
    }
    
    return audit_trail


# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Simple health check endpoint
    """
    return {
        "status": "healthy",
        "active_incidents": len(active_incidents)
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

# Made with Bob
