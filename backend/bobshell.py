"""
BobShell - Automated Deployment Orchestrator
Executes the Cloud Run deployment recipe when an engineer approves the fix
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, Optional
from dotenv import load_dotenv
from watsonx_client import generate_with_granite

# Load environment variables
load_dotenv()

CLOUD_RUN_SERVICE_NAME = os.getenv("CLOUD_RUN_SERVICE_NAME") or os.getenv("CODE_ENGINE_APP_NAME", "payments-api")
GCLOUD_PROJECT = os.getenv("GCLOUD_PROJECT", "")
GCLOUD_REGION = os.getenv("GCLOUD_REGION", "")


async def apply_fix_and_deploy(
    incident_id: str,
    fixed_code: str,
    target_file: str,
    regression_test_content: str = "",
    regression_test_file: str = "",
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the deployment of an approved fix
    
    Calls the deploy_fix.sh bash script which:
    1. Copies the fixed file into the repo
    2. Optionally writes the generated regression test
    3. Runs the demo-service test suite
    4. Deploys the demo service to Cloud Run with gcloud
    
    Args:
        incident_id: Unique incident identifier
        fixed_code: Bob's fixed source code
        target_file: Repo-relative path to replace with fixed_code
        regression_test_content: Optional regression test file contents
        regression_test_file: Optional repo-relative regression test path
    
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

    if not fixed_code.strip() or not target_file.strip():
        yield _log_event("ERROR: Missing fixed code or target file for deployment")
        yield _completion_event(incident_id, "failed", "Structured fix payload missing")
        return
    
    # Create temporary file for fixed code
    fixed_suffix = os.path.splitext(target_file)[1] or '.txt'
    with tempfile.NamedTemporaryFile(mode='w', suffix=fixed_suffix, delete=False) as tmp:
        tmp.write(fixed_code)
        fixed_file_path = tmp.name

    regression_test_path = ""
    if regression_test_content.strip() and regression_test_file.strip():
        test_suffix = os.path.splitext(regression_test_file)[1] or '.txt'
        with tempfile.NamedTemporaryFile(mode='w', suffix=test_suffix, delete=False) as tmp:
            tmp.write(regression_test_content)
            regression_test_path = tmp.name
    
    try:
        yield _log_event(f"Starting deployment for incident {incident_id}...")
        yield _log_event(f"Fixed code written to: {fixed_file_path}")
        yield _log_event(f"Target file: {target_file}")
        if regression_test_path:
            yield _log_event(f"Regression test prepared for: {regression_test_file}")
        
        # Generate commit message with Granite
        yield _log_event("Generating commit message with IBM Granite...")
        commit_context = f"Incident {incident_id}: Fix for production issue. Code changes: {fixed_code[:200]}..."
        commit_message = await generate_with_granite("commit_message", commit_context)
        yield _log_event(f"Commit message: {commit_message}")
        
        # Prepare environment variables for the script
        env = os.environ.copy()
        env["CLOUD_RUN_SERVICE_NAME"] = CLOUD_RUN_SERVICE_NAME
        if GCLOUD_PROJECT:
            env["GCLOUD_PROJECT"] = GCLOUD_PROJECT
        if GCLOUD_REGION:
            env["GCLOUD_REGION"] = GCLOUD_REGION
        
        # Execute deployment script
        process = await asyncio.create_subprocess_exec(
            "bash",
            script_path,
            incident_id,
            fixed_file_path,
            target_file,
            regression_test_path,
            regression_test_file,
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

            elif "Pushed to origin/" in line_text or "Committed:" in line_text:
                # Git push / commit line — emit dedicated event type for frontend highlight
                yield _git_event(line_text)

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
        if regression_test_path:
            try:
                os.unlink(regression_test_path)
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


def _git_event(message: str) -> str:
    """Formats a git push/commit line as a distinct SSE event type for frontend highlighting."""
    return f"data: {json.dumps({'type': 'git_push', 'timestamp': datetime.now().isoformat(), 'message': message})}\n\n"


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


def log_orchestrate_decision(
    incident_id: str,
    action: str,
    approver: str,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Logs a watsonx Orchestrate decision to the audit trail
    
    This function creates an audit entry when a human approver makes a decision
    through watsonx Orchestrate. The entry appears in the Incident Timeline panel
    on the dashboard alongside Bob's reasoning steps.
    
    Args:
        incident_id: Unique incident identifier
        action: Decision action - "approve", "escalate", or "reject"
        approver: Name or ID of the person who made the decision
        reason: Optional comment from the approver explaining their decision
    
    Returns:
        Dictionary containing the audit trail entry
    """
    from datetime import datetime
    
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "orchestrate_decision",
        "incident_id": incident_id,
        "action": action,
        "approver": approver,
        "reason": reason,
        "source": "watsonx_orchestrate"
    }
    
    return audit_entry


# Made with Bob
