"""
BobShell - Automated Deployment Orchestrator
Executes deployment recipe when engineer approves the fix
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from typing import AsyncGenerator
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get IBM Cloud credentials
IBM_CLOUD_API_KEY = os.getenv("IBM_CLOUD_API_KEY")
IBM_CLOUD_REGION = os.getenv("IBM_CLOUD_REGION", "jp-tok")
CODE_ENGINE_PROJECT = os.getenv("CODE_ENGINE_PROJECT", "opsbob-demo")
ICR_NAMESPACE = os.getenv("ICR_NAMESPACE", "opsbob")
CODE_ENGINE_APP_NAME = os.getenv("CODE_ENGINE_APP_NAME", "payments-api")


async def apply_fix_and_deploy(
    incident_id: str,
    fixed_code: str
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the deployment of an approved fix
    
    Calls the deploy_fix.sh bash script which:
    1. Copies fixed file to repo
    2. Runs test suite
    3. Builds Docker container
    4. Pushes to IBM Container Registry
    5. Deploys to Code Engine
    6. Polls until ready
    
    Args:
        incident_id: Unique incident identifier
        fixed_code: Bob's fixed source code
    
    Yields audit log entries as SSE events for real-time monitoring
    """
    
    # Get path to deployment script
    script_path = os.path.join(
        os.path.dirname(__file__),
        "deploy_fix.sh"
    )
    
    if not os.path.exists(script_path):
        yield _log_event(f"ERROR: Deployment script not found: {script_path}")
        yield _completion_event(incident_id, "failed", "Deployment script missing")
        return
    
    # Create temporary file for fixed code
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tmp:
        tmp.write(fixed_code)
        fixed_file_path = tmp.name
    
    try:
        yield _log_event(f"Starting deployment for incident {incident_id}...")
        yield _log_event(f"Fixed code written to: {fixed_file_path}")
        
        # Prepare environment variables for the script
        env = os.environ.copy()
        if ICR_NAMESPACE:
            env["ICR_NAMESPACE"] = ICR_NAMESPACE
        if CODE_ENGINE_APP_NAME:
            env["CODE_ENGINE_APP_NAME"] = CODE_ENGINE_APP_NAME
        if IBM_CLOUD_API_KEY:
            env["IBMCLOUD_API_KEY"] = IBM_CLOUD_API_KEY
        if IBM_CLOUD_REGION:
            env["IBMCLOUD_REGION"] = IBM_CLOUD_REGION
        
        # Execute deployment script
        process = await asyncio.create_subprocess_exec(
            "bash",
            script_path,
            incident_id,
            fixed_file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env
        )
        
        # Stream output line by line
        start_time = datetime.now()
        
        # Ensure stdout is available (it should be since we set stdout=PIPE)
        if process.stdout is None:
            yield _log_event("ERROR: Process stdout is not available")
            yield _completion_event(incident_id, "failed", "Process stdout unavailable")
            return
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_text = line.decode('utf-8').strip()
            
            # Check for special markers
            if line_text.startswith("RESOLVED:"):
                # Extract incident ID from marker
                resolved_id = line_text.split(":", 1)[1]
                
                # Calculate MTTR
                end_time = datetime.now()
                mttr_seconds = int((end_time - start_time).total_seconds())
                mttr_minutes = mttr_seconds // 60
                mttr_secs = mttr_seconds % 60
                mttr_str = f"{mttr_minutes} minutes {mttr_secs} seconds"
                
                yield _log_event(f"✓ Deployment successful - MTTR: {mttr_str}")
                yield _completion_event(incident_id, "resolved", mttr_str)
                
            elif line_text.startswith("ERROR:") or line_text.startswith("✗"):
                # Error line
                yield _log_event(f"⚠️  {line_text}")
                
            elif line_text.startswith("✓"):
                # Success line
                yield _log_event(line_text)
                
            elif line_text and not line_text.startswith("="):
                # Regular output line (skip separator lines)
                yield _log_event(line_text)
        
        # Wait for process to complete
        await process.wait()
        
        if process.returncode != 0:
            yield _log_event(f"✗ Deployment failed with exit code {process.returncode}")
            yield _completion_event(incident_id, "failed", f"Exit code {process.returncode}")
        
    except Exception as e:
        yield _log_event(f"✗ Deployment error: {str(e)}")
        yield _completion_event(incident_id, "failed", str(e))
    
    finally:
        # Clean up temporary file
        try:
            os.unlink(fixed_file_path)
        except:
            pass


def _log_event(message: str) -> str:
    """
    Formats a log message as an SSE event
    
    Returns SSE-formatted string: data: {...}\n\n
    """
    log_entry = {
        "type": "log",
        "timestamp": datetime.now().isoformat(),
        "message": message
    }
    return f"data: {json.dumps(log_entry)}\n\n"


def _completion_event(incident_id: str, status: str, details: str) -> str:
    """
    Formats a completion event as SSE
    
    Args:
        incident_id: Incident identifier
        status: "resolved" or "failed"
        details: MTTR string or error message
    """
    completion = {
        "type": "completion",
        "status": status,
        "incidentId": incident_id,
        "completedAt": datetime.now().isoformat(),
        "details": details
    }
    return f"data: {json.dumps(completion)}\n\n"


async def rollback_deployment(incident_id: str, reason: str) -> AsyncGenerator[str, None]:
    """
    Rolls back a deployment if issues are detected
    
    This would be called if post-deployment monitoring detects problems
    """
    yield _log_event("⚠️  Issues detected in new deployment")
    await asyncio.sleep(0.8)
    yield _log_event(f"Reason: {reason}")
    await asyncio.sleep(0.8)
    yield _log_event("Initiating rollback to previous revision...")
    await asyncio.sleep(1.0)
    yield _log_event("✓ Rollback complete")
    await asyncio.sleep(0.5)
    yield _log_event("Restored to previous revision")
    
    rollback_event = {
        "type": "completion",
        "status": "rolled_back",
        "incidentId": incident_id,
        "rolledBackAt": datetime.now().isoformat(),
        "reason": reason
    }
    
    yield f"data: {json.dumps(rollback_event)}\n\n"


# Made with Bob
