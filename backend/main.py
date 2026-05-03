"""
OpsBob Backend - FastAPI Orchestration Layer
Handles incident webhooks, streams Bob's analysis, runs 4-agent pipeline,
and orchestrates deployment via BobShell.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from bob_client import call_bob_orchestrator, is_bob_shell_available
from bobshell import apply_fix_and_deploy
from mcp_client import get_mcp_client
from watsonx_client import generate_with_granite
from orchestrate_agents import (
    run_agent_pipeline, run_post_incident,
    run_static_analysis, run_tests, route_approval,
    get_incident_history, get_similar_incidents
)
from orchestrate_client import (
    run_pre_incident_pipeline, run_post_incident_pipeline, is_orchestrate_configured
)
from health_monitor import get_all_service_health
from incident_intelligence import build_context_enrichment, get_stats as get_memory_stats

load_dotenv()

SOURCE_FILES_PATH = os.getenv("SOURCE_FILES_PATH", "demo-service")
DEMO_SERVICE_URL = os.getenv("DEMO_SERVICE_URL", "http://localhost:3001")

app = FastAPI(title="OpsBob Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_incidents: Dict[str, Dict[str, Any]] = {}
incident_queue: list = []


# ── Pydantic Models ──────────────────────────────────────────────
class IncidentWebhook(BaseModel):
    id: Optional[str] = None
    incidentId: Optional[str] = None
    title: Optional[str] = "Memory leak detected"
    entityName: Optional[str] = None
    service: Optional[str] = None
    severity: Optional[Any] = "HIGH"
    type: Optional[str] = "MEMORY_LEAK"
    start: Optional[int] = None
    message: Optional[str] = ""

class ApprovalRequest(BaseModel):
    approved: bool

class OrchestrateDecision(BaseModel):
    incident_id: str
    action: str  # "approve" | "escalate" | "reject"
    approver: str
    reason: str

class StaticAnalysisRequest(BaseModel):
    incident_id: Optional[str] = "INC-UNKNOWN"
    code_diff: Optional[str] = ""
    plan_text: Optional[str] = ""
    message: Optional[str] = None  # natural-language input from Orchestrate

class TestRunnerRequest(BaseModel):
    incident_id: Optional[str] = "INC-UNKNOWN"
    test_command: Optional[str] = "npm test"
    working_dir: Optional[str] = None
    message: Optional[str] = None

class ApprovalRoutingRequest(BaseModel):
    incident_id: Optional[str] = "INC-UNKNOWN"
    risk_score: Optional[str] = None
    static_verdict: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    risk_assessment: Optional[Dict[str, Any]] = None
    static_result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class PostIncidentRequest(BaseModel):
    incident_id: Optional[str] = "INC-UNKNOWN"
    timeline: Optional[str] = None
    resolution_data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


# ── Startup ──────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("  OpsBob Backend v2.0 — Production Intelligence Platform")
    print("=" * 60)
    print(f"  Bob shell: {'available' if is_bob_shell_available() else 'NOT FOUND'}")
    print(f"  Source path: {SOURCE_FILES_PATH}")
    print(f"  Demo service: {DEMO_SERVICE_URL}")
    memory_stats = get_memory_stats()
    print(f"  Institutional memory: {memory_stats['total_incidents']} past incidents")
    print("=" * 60)


# ── POST /webhook ────────────────────────────────────────────────
@app.post("/webhook")
async def receive_webhook(incident: IncidentWebhook):
    """Receives incident alerts from Instana or manual trigger."""
    incident_data = incident.dict()
    service = incident_data.get("entityName") or incident_data.get("service") or "payments-api"
    incident_id = incident_data.get("id") or incident_data.get("incidentId") or f"INC-{service[:8].upper()}-{int(datetime.now().timestamp() * 1000)}"
    severity = incident_data.get("severity", "HIGH")
    inc_type = incident_data.get("type", "MEMORY_LEAK")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] WEBHOOK RECEIVED:")
    print(f"  Incident ID: {incident_id}")
    print(f"  Service: {service}")
    print(f"  Severity: {severity}")

    # Queue if another incident is active
    active_analyzing = [i for i in active_incidents.values() if i.get("status") in ("analyzing", "deploying")]
    if active_analyzing:
        incident_queue.append({"id": incident_id, "data": incident_data})
        print(f"  Queued (position {len(incident_queue)})")
        return {"status": "queued", "incidentId": incident_id, "position": len(incident_queue)}

    try:
        # Try MCP for enrichment, fall back to demo service
        stack_traces = ""
        mem_growth_mb = 0
        try:
            mcp = get_mcp_client()
            st_result = mcp.get_stack_traces(incident_id)
            should_fallback = st_result.get("error", False)
            if not st_result.get("error"):
                stack_traces = st_result.get("stack_trace", "")
            m_result = mcp.get_service_metrics(service, "10m")
            should_fallback = should_fallback or m_result.get("error", False)
            if not m_result.get("error"):
                mem_growth_mb = m_result.get("current_memory_mb", 0) - m_result.get("baseline_memory_mb", 0)
            if should_fallback or not stack_traces:
                raise RuntimeError("MCP enrichment unavailable; using demo-service fallback")
        except Exception as mcp_err:
            print(f"  MCP fallback: {mcp_err}")
            # Fallback to demo service /debug/traces and /metrics
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{DEMO_SERVICE_URL}/debug/traces", timeout=aiohttp.ClientTimeout(total=3)) as r:
                        if r.status == 200:
                            data = await r.json()
                            stack_traces = data.get("stack_trace", "")
                    async with session.get(f"{DEMO_SERVICE_URL}/metrics", timeout=aiohttp.ClientTimeout(total=3)) as r:
                        if r.status == 200:
                            data = await r.json()
                            mem_growth_mb = data.get("heap_used_mb", 0) - 50
            except:
                stack_traces = "Stack traces unavailable"

        # Read source files
        source_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), SOURCE_FILES_PATH)
        source_files = {}
        for fp in ["server.js", "routes/payments.js", "middleware/session.js", "store/sessionStore.js"]:
            full = os.path.join(source_base, fp)
            try:
                with open(full, 'r', encoding='utf-8') as f:
                    source_files[fp] = f.read()
            except:
                source_files[fp] = f"// File not found: {fp}"

        # Institutional memory enrichment
        memory_enrichment = build_context_enrichment(inc_type, service) or ""

        bob_context = f"""INCIDENT SUMMARY:
Service: {service}
Incident ID: {incident_id}
Detected: memory growth of {mem_growth_mb:.0f}MB over 10 minutes
Severity: {severity}
Type: {inc_type}

INSTANA STACK TRACE:
{stack_traces}

SOURCE CODE — server.js:
{source_files.get('server.js', '')}

SOURCE CODE — store/sessionStore.js:
{source_files.get('store/sessionStore.js', '')}

SOURCE CODE — middleware/session.js:
{source_files.get('middleware/session.js', '')}

SOURCE CODE — routes/payments.js:
{source_files.get('routes/payments.js', '')}
{memory_enrichment}
Your task: identify the root cause, propose a minimal fix, and write the corrected code. Then generate one regression test that would catch this bug."""

        active_incidents[incident_id] = {
            **incident_data,
            "incident_id": incident_id,
            "status": "received",
            "received_at": datetime.now().isoformat(),
            "timestamp": asyncio.get_event_loop().time(),
            "context": bob_context,
            "service": service,
            "severity": severity,
            "type": inc_type,
            "mem_growth_mb": mem_growth_mb,
            "stack_traces": stack_traces,
            "pipeline_results": None,
            "approval_routing": None
        }

        print(f"  Context assembled ({len(bob_context)} chars)")
        return {"status": "received", "incidentId": incident_id, "contextLength": len(bob_context)}

    except Exception as e:
        print(f"  ERROR: {e}")
        active_incidents[incident_id] = {**incident_data, "incident_id": incident_id, "status": "error", "error": str(e)}
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /stream/{incidentId} ────────────────────────────────────
@app.get("/stream/{incidentId}")
async def stream_analysis(incidentId: str):
    """Streams Bob's analysis + agent pipeline via SSE."""
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = active_incidents[incidentId]
    if "context" not in incident:
        raise HTTPException(status_code=400, detail="Context not assembled")

    async def event_generator():
        def encode_sse(payload):
            return f"data: {json.dumps(payload)}\n\n"

        try:
            print(f"Starting analysis for {incidentId}")
            incident["status"] = "analyzing"
            incident.pop("analysis_error", None)
            context = incident["context"]

            async for event in call_bob_orchestrator(context):
                event_data = json.loads(event.replace("data: ", "").strip())

                if event_data.get("phase") == "error":
                    incident["status"] = "analysis_failed"
                    incident["analysis_error"] = event_data.get("content", "Analysis failed")
                    yield event
                    return

                if event_data.get("phase") == "plan" and event_data.get("done"):
                    incident["plan_response"] = event_data.get("content", "")
                    incident["risk_assessment"] = event_data.get("risk_assessment", {})

                if event_data.get("phase") == "code" and event_data.get("done"):
                    incident["bob_response"] = event_data.get("content", "")
                    incident["fixed_code"] = event_data.get("fixed_code", "")
                    incident["fix_target_file"] = event_data.get("target_file", "")
                    incident["regression_test_file"] = event_data.get("regression_test_file", "")
                    incident["regression_test_content"] = event_data.get("regression_test_content", "")

                yield event

            print(f"Bob analysis complete for {incidentId}")

            # Run 4-agent pipeline after Bob completes
            if incident.get("bob_response") and incident.get("plan_response"):
                print(f"Starting 4-agent pipeline for {incidentId}")

                pipeline_events = asyncio.Queue()

                async def emit_agent_event(evt):
                    await pipeline_events.put(evt)

                pipeline_task = asyncio.create_task(
                    run_agent_pipeline(incidentId, incident, event_callback=emit_agent_event)
                )

                while True:
                    if pipeline_task.done() and pipeline_events.empty():
                        break

                    try:
                        pipeline_event = await asyncio.wait_for(pipeline_events.get(), timeout=0.2)
                    except asyncio.TimeoutError:
                        continue

                    if pipeline_event.get("phase") == "agent_pipeline_complete":
                        pipeline_result = pipeline_event.get("result", {})
                        yield encode_sse({
                            "phase": "pipeline_complete",
                            "agents": pipeline_result.get("agents", {}),
                            "verdict": pipeline_result.get("pipeline_verdict", "review"),
                            "routing_reason": pipeline_result.get("routing_reason", ""),
                            "all_passed": pipeline_result.get("all_agents_passed", False),
                            "done": True
                        })
                        continue

                    yield encode_sse({
                        **pipeline_event,
                        "done": pipeline_event.get("status") != "running"
                    })

                pipeline = await pipeline_task
                incident["pipeline_results"] = pipeline
                incident["approval_routing"] = pipeline.get("agents", {}).get("approval_router", {})
                incident["status"] = "analyzed"

                # ── Orchestrate commander: final decision ────────────────────
                print(f"Calling Orchestrate commander for {incidentId}")
                yield encode_sse({
                    "phase": "orchestrate_status",
                    "status": "running",
                    "message": "Commander is reviewing verification outputs",
                    "done": False
                })
                orc_result = await run_pre_incident_pipeline(incidentId, incident)
                incident["orchestrate_result"] = orc_result
                orc_decision = orc_result.get("decision", "review")

                orchestrate_event = {
                    "phase": "orchestrate_decision",
                    "decision": orc_decision,
                    "session_id": orc_result.get("session_id"),
                    "orchestrate_used": orc_result.get("orchestrate_used", False),
                    "error": orc_result.get("error"),
                    "done": True
                }
                yield encode_sse(orchestrate_event)

                # Auto-deploy when commander approves — no human click required
                if orc_decision == "approve":
                    incident["status"] = "deploying"
                    incident["approved_at"] = datetime.now().isoformat()
                    incident["approver"] = "orchestrate_commander"
                    print(f"[ORCHESTRATE] Auto-approving {incidentId} — triggering deploy")
                    yield encode_sse({"phase": "auto_deploy", "incidentId": incidentId, "done": True})
            else:
                incident["status"] = "analysis_failed"
                incident["analysis_error"] = "Analysis did not produce a plan and code diff"
                yield encode_sse({"phase": "error", "content": incident["analysis_error"], "done": True})

        except Exception as e:
            print(f"Stream error: {e}")
            incident["status"] = "analysis_failed"
            incident["analysis_error"] = str(e)
            yield encode_sse({"phase": "error", "content": str(e), "done": True})

    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ── POST /approve/{incidentId} ──────────────────────────────────
@app.post("/approve/{incidentId}")
async def approve_fix(incidentId: str, approval: ApprovalRequest):
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = active_incidents[incidentId]

    if incident.get("analysis_error"):
        raise HTTPException(status_code=400, detail="Cannot approve an incident with a failed analysis")

    if not incident.get("pipeline_results"):
        raise HTTPException(status_code=400, detail="Cannot approve before the verification pipeline completes")

    if approval.approved:
        print(f"FIX APPROVED for {incidentId}")
        incident["status"] = "deploying"
        incident["approved_at"] = datetime.now().isoformat()
        return {"status": "deploying", "incidentId": incidentId}
    else:
        incident["status"] = "rejected"
        return {"status": "rejected", "incidentId": incidentId}


# ── POST /orchestrate/decision ──────────────────────────────────
@app.post("/orchestrate/decision")
async def receive_orchestrate_decision(decision: OrchestrateDecision):
    """Receives approval/rejection/escalation from watsonx Orchestrate."""
    iid = decision.incident_id
    if iid not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = active_incidents[iid]

    if decision.action == "approve":
        incident["status"] = "deploying"
        incident["approver"] = decision.approver
        incident["approval_reason"] = decision.reason
        return {"status": "deploying", "incidentId": iid}
    elif decision.action == "escalate":
        incident["status"] = "escalated"
        incident["escalated_to"] = decision.approver
        incident["escalation_reason"] = decision.reason
        return {"status": "escalated", "incidentId": iid}
    else:
        incident["status"] = "rejected"
        incident["rejected_by"] = decision.approver
        return {"status": "rejected", "incidentId": iid}


# ── POST /orchestrate/prepare/{incidentId} ──────────────────────
@app.post("/orchestrate/prepare/{incidentId}")
async def prepare_orchestrate(incidentId: str):
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = active_incidents[incidentId]
    if "plan_response" not in incident:
        raise HTTPException(status_code=400, detail="Analysis not complete")

    try:
        summary = await generate_with_granite("incident_summary",
            f"Service: {incident.get('service')}\nRoot Cause: {incident.get('plan_response', '')[:300]}")
        return {
            "incident_id": incidentId,
            "service_name": incident.get("service"),
            "fix_summary": summary,
            "confidence": incident.get("risk_assessment", {}).get("confidence", "medium"),
            "pipeline_results": incident.get("pipeline_results"),
            "dashboard_url": f"http://localhost:3000/incidents/{incidentId}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /orchestrate/static-analysis ───────────────────────────
@app.post("/orchestrate/static-analysis")
async def orchestrate_static_analysis(request: StaticAnalysisRequest):
    """Tool endpoint for watsonx Orchestrate StaticAnalysisAgent."""
    # Accept natural-language message from Orchestrate as the code diff/context
    diff = request.code_diff or request.message or request.plan_text or "No diff provided"
    incident_id = request.incident_id or "INC-UNKNOWN"
    return await run_static_analysis(incident_id, diff, request.plan_text or "")


# ── POST /orchestrate/run-tests ─────────────────────────────────
@app.post("/orchestrate/run-tests")
async def orchestrate_run_tests(request: TestRunnerRequest):
    """Tool endpoint for watsonx Orchestrate TestRunnerAgent."""
    return await run_tests(request.incident_id, working_dir=request.working_dir)


# ── POST /orchestrate/route-approval ────────────────────────────
@app.post("/orchestrate/route-approval")
async def orchestrate_route_approval(request: ApprovalRoutingRequest):
    """Tool endpoint for watsonx Orchestrate ApprovalRouterAgent."""
    risk_assessment = request.risk_assessment or {
        "confidence": "medium",
        "risk_level": request.risk_score or "medium"
    }
    static_result = request.static_result or {
        "verdict": request.static_verdict or "PASS"
    }
    test_result = request.test_results or {
        "verdict": "PASS",
        "failed": 0
    }

    return await route_approval(
        request.incident_id,
        risk_assessment,
        static_result,
        test_result
    )


# ── POST /orchestrate/post-incident ─────────────────────────────
@app.post("/orchestrate/post-incident")
async def orchestrate_post_incident(request: PostIncidentRequest):
    """Tool endpoint for watsonx Orchestrate PostIncidentReportAgent."""
    incident_data = dict(request.resolution_data or {})
    if request.timeline and "timeline" not in incident_data:
        incident_data["timeline"] = request.timeline

    result = await run_post_incident(request.incident_id, incident_data)
    return {
        **result,
        "runbook_update": result.get("runbook_entry", "")
    }


# ── GET /orchestrate/stream/{incidentId} ────────────────────────
@app.get("/orchestrate/stream/{incidentId}")
async def stream_orchestrate_direct(incidentId: str):
    """
    Direct IBM watsonx Orchestrate 4-agent pipeline trigger via SSE.
    Streams: started → progress (every 3 s) → agent_result (×4) → complete.
    Works even when Bob analysis has not run yet — builds message from
    whatever incident data is available in active_incidents.
    """
    from orchestrate_client import _invoke_agent, _extract_text, _parse_decision

    incident = active_incidents.get(incidentId, {})
    service  = incident.get("service") or incident.get("entityName") or "unknown-service"
    severity = incident.get("severity", "HIGH")
    inc_type = incident.get("type", "MEMORY_LEAK")
    title    = incident.get("title", f"Incident {incidentId}")
    raw_msg  = incident.get("message", "")

    lines = [
        f"INCIDENT: {incidentId}",
        f"SERVICE: {service}",
        f"SEVERITY: {severity}",
        f"TYPE: {inc_type}",
        f"DESCRIPTION: {raw_msg or title}",
    ]
    code_diff = (incident.get("bob_response") or incident.get("fixed_code") or "")[:1200]
    plan      = (incident.get("plan_response") or "")[:800]
    if code_diff:
        lines += ["", "PROPOSED FIX (code diff):", code_diff]
    if plan:
        lines += ["", "ROOT CAUSE ANALYSIS:", plan]

    message = "\n".join(lines)

    _TOOL_AGENT = {
        "orchestrate_static_analysis": "static_analysis",
        "orchestrate_run_tests":        "test_runner",
        "orchestrate_route_approval":   "approval_router",
        "orchestrate_post_incident":    "post_incident",
    }

    async def event_generator():
        def enc(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        yield enc({"phase": "started", "incident_id": incidentId,
                   "message": "Invoking IBM watsonx Orchestrate commander…"})
        try:
            task    = asyncio.create_task(_invoke_agent(message))
            elapsed = 0
            while not task.done():
                await asyncio.sleep(3)
                elapsed += 3
                yield enc({"phase": "progress", "elapsed": elapsed,
                           "message": f"Commander orchestrating agents… ({elapsed}s)"})

            result = await task

            step_history = (result.get("result", {})
                                  .get("data", {})
                                  .get("message", {})
                                  .get("step_history", []))

            emitted: set = set()
            for step in step_history:
                for detail in step.get("step_details", []):
                    if detail.get("type") == "tool_response":
                        tool_name = detail.get("name", "")
                        agent_id  = _TOOL_AGENT.get(tool_name)
                        if agent_id and agent_id not in emitted:
                            emitted.add(agent_id)
                            raw_content = detail.get("content", "{}")
                            try:
                                agent_result = json.loads(raw_content)
                            except Exception:
                                agent_result = {"raw": raw_content}
                            yield enc({
                                "phase":   "agent_result",
                                "agent":   agent_id,
                                "result":  agent_result,
                                "verdict": (agent_result.get("verdict")
                                            or agent_result.get("recommendation", "unknown")),
                            })

            commander_text = _extract_text(result)
            decision       = _parse_decision(commander_text)
            yield enc({"phase": "complete", "decision": decision,
                       "commander_text": commander_text,
                       "incident_id": incidentId, "done": True})

        except Exception as exc:
            print(f"[ORCHESTRATE STREAM] Error for {incidentId}: {exc}")
            yield enc({"phase": "error", "message": str(exc), "done": True})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


# ── GET /deploy-stream/{incidentId} ─────────────────────────────
@app.get("/deploy-stream/{incidentId}")
async def stream_deployment(incidentId: str):
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = active_incidents[incidentId]
    if incident.get("status") != "deploying":
        raise HTTPException(status_code=400, detail="Must be approved first")

    async def deployment_generator():
        try:
            fixed_code = incident.get("fixed_code", "")
            target_file = incident.get("fix_target_file", "")

            if not fixed_code or not target_file:
                raise ValueError("No structured fix payload available for deployment")

            async for event in apply_fix_and_deploy(
                incidentId,
                fixed_code,
                target_file=target_file,
                regression_test_content=incident.get("regression_test_content", ""),
                regression_test_file=incident.get("regression_test_file", ""),
            ):
                yield event

            incident["status"] = "resolved"
            incident["resolved_at"] = datetime.now().isoformat()

            # Run post-incident via Orchestrate commander (falls back to local agent)
            try:
                if is_orchestrate_configured():
                    report = await run_post_incident_pipeline(incidentId, incident)
                else:
                    report = await run_post_incident(incidentId, incident)
                incident["post_incident_report"] = report
                yield f"data: {json.dumps({'type': 'agent', 'agent': 'post_incident', 'status': 'complete', 'result': report})}\n\n"
            except Exception as pe:
                print(f"Post-incident report error: {pe}")

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            incident["status"] = "deployment_failed"

    return StreamingResponse(deployment_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ── GET /incidents ───────────────────────────────────────────────
@app.get("/incidents")
async def get_incidents():
    return active_incidents


# ── GET /audit/{incidentId} ─────────────────────────────────────
@app.get("/audit/{incidentId}")
async def get_audit_trail(incidentId: str):
    if incidentId not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = active_incidents[incidentId]
    return {
        "incidentId": incidentId,
        "incident": {k: v for k, v in incident.items() if k != "context"},
        "pipeline_results": incident.get("pipeline_results"),
        "post_incident_report": incident.get("post_incident_report"),
        "status": incident.get("status")
    }


# ── GET /runbook ─────────────────────────────────────────────────
@app.get("/runbook")
async def get_runbook():
    """Returns institutional memory from incident-history.json."""
    return get_incident_history()


# ── GET /system-health ───────────────────────────────────────────
@app.get("/system-health")
async def system_health():
    """Returns health status of all IBM services."""
    return await get_all_service_health()


# ── GET /memory-stats ────────────────────────────────────────────
@app.get("/memory-stats")
async def memory_stats():
    """Returns institutional memory statistics."""
    return get_memory_stats()


# ── GET /incident-queue ──────────────────────────────────────────
@app.get("/incident-queue")
async def get_queue():
    return {"queue": incident_queue, "length": len(incident_queue)}


# ── Demo-service SSE proxy + payment proxy ───────────────────────
@app.get("/demo-services/logs/{port}")
async def stream_service_logs(port: int):
    if not (1024 <= port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port")

    async def event_gen():
        import aiohttp
        connected = False
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"http://localhost:{port}/logs/stream",
                        timeout=aiohttp.ClientTimeout(total=None, connect=3),
                    ) as resp:
                        if resp.status != 200:
                            yield f"data: {json.dumps({'line': f'[WARN] Service on :{port} returned HTTP {resp.status}'})}\n\n"
                            await asyncio.sleep(3)
                            continue
                        connected = True
                        async for chunk in resp.content.iter_any():
                            if chunk:
                                yield chunk.decode("utf-8")
                        connected = False
                        yield f"data: {json.dumps({'line': f'[WARN] Service on :{port} stream ended, retrying...'})}\n\n"
                        await asyncio.sleep(2)
            except aiohttp.ClientConnectorError:
                msg = "[WARN] Service stopped, retrying..." if connected else f"[WARN] Cannot connect to :{port} — is the service running?"
                connected = False
                yield f"data: {json.dumps({'line': msg})}\n\n"
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                yield f"data: {json.dumps({'line': f'[ERROR] {exc}'})}\n\n"
                await asyncio.sleep(3)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/demo-services/{port}/payment")
async def proxy_demo_payment(port: int, request: Request):
    if not (1024 <= port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port")
    import aiohttp
    try:
        body = await request.json()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://localhost:{port}/payment",
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/demo-services/{port}/trigger-incident")
async def proxy_demo_trigger(port: int):
    if not (1024 <= port <= 65535):
        raise HTTPException(status_code=400, detail="Invalid port")
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://localhost:{port}/trigger-incident",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return await resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── GET /health ──────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "active_incidents": len(active_incidents), "queued": len(incident_queue)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True, log_level="info")

# Made with Bob
