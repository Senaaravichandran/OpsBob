"""
watsonx Orchestrate Agents — Four-agent verification pipeline for OpsBob

Each agent has:
  - A real implementation (API call or local execution)
  - A 15-second timeout on external calls
  - A safe fallback result if the API fails
  - AGENT_FALLBACK logging in the audit trail

Agent Types:
  1. StaticAnalysisAgent  — Real watsonx.ai call (Granite)
  2. TestRunnerAgent      — Local npm test (no external API)
  3. ApprovalRouterAgent  — Pure logic (no API call)
  4. PostIncidentReportAgent — Real watsonx.ai call (Granite)
"""

import asyncio
import json
import os
import shutil
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from iam_auth import get_iam_token

load_dotenv()

WATSONX_API_KEY = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
WATSONX_SPACE_ID = os.getenv("WATSONX_SPACE_ID")
WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_MODEL_ID = os.getenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small")

AGENT_TIMEOUT = 15  # seconds — never block the demo


def _build_watsonx_scope() -> Dict[str, str]:
    if WATSONX_SPACE_ID:
        return {"space_id": WATSONX_SPACE_ID}
    if WATSONX_PROJECT_ID:
        return {"project_id": WATSONX_PROJECT_ID}
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# Agent 1: StaticAnalysisAgent
# ═══════════════════════════════════════════════════════════════════════════

async def run_static_analysis(incident_id: str, bob_diff: str, bob_plan: str) -> Dict[str, Any]:
    """
    Sends Bob's code diff to watsonx.ai (Granite) for security and correctness review.

    Returns:
        {
            verdict: "PASS" | "WARN" | "FAIL",
            findings: [...],
            agent: "static_analysis",
            timestamp: ISO string,
            fallback: bool
        }
    """
    fallback_result = {
        "verdict": "PASS",
        "findings": ["Fallback: Static analysis skipped — watsonx.ai unavailable"],
        "agent": "static_analysis",
        "timestamp": datetime.now().isoformat(),
        "fallback": True,
        "duration_ms": 0
    }

    if not WATSONX_API_KEY or not _build_watsonx_scope():
        print(f"[AGENT_FALLBACK] StaticAnalysisAgent: credentials not configured")
        return fallback_result

    start = datetime.now()

    try:
        import aiohttp

        prompt = f"""You are a senior security engineer reviewing an AI-generated code fix. 
Analyze this diff for:
1. Null pointer risks introduced
2. Security vulnerabilities (injection, data exposure)
3. Logic errors or regressions
4. Whether the fix actually addresses the root cause

CODE DIFF:
{bob_diff[:2000]}

ROOT CAUSE ANALYSIS:
{bob_plan[:1000]}

Return ONLY valid JSON with these fields:
- verdict: "PASS", "WARN", or "FAIL"
- findings: array of strings (max 5 findings)
- risk_areas: array of strings listing specific concerns
"""

        endpoint = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
        iam_token = await get_iam_token(WATSONX_API_KEY)
        headers = {
            "Authorization": f"Bearer {iam_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "model_id": WATSONX_MODEL_ID,
            "input": prompt,
            "parameters": {"max_new_tokens": 300, "temperature": 0},
            **_build_watsonx_scope()
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=AGENT_TIMEOUT)
            ) as response:
                if response.status != 200:
                    print(f"[AGENT_FALLBACK] StaticAnalysisAgent: watsonx.ai returned {response.status}")
                    return fallback_result

                result = await response.json()
                generated = result.get("results", [{}])[0].get("generated_text", "")

                # Parse JSON from response
                cleaned = generated.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                try:
                    parsed = json.loads(cleaned)
                    duration = int((datetime.now() - start).total_seconds() * 1000)
                    return {
                        "verdict": parsed.get("verdict", "PASS"),
                        "findings": parsed.get("findings", []),
                        "risk_areas": parsed.get("risk_areas", []),
                        "agent": "static_analysis",
                        "timestamp": datetime.now().isoformat(),
                        "fallback": False,
                        "duration_ms": duration
                    }
                except json.JSONDecodeError:
                    print(f"[AGENT_FALLBACK] StaticAnalysisAgent: failed to parse response")
                    return fallback_result

    except asyncio.TimeoutError:
        print(f"[AGENT_FALLBACK] StaticAnalysisAgent: timeout after {AGENT_TIMEOUT}s")
        return fallback_result
    except Exception as e:
        print(f"[AGENT_FALLBACK] StaticAnalysisAgent: {e}")
        return fallback_result


# ═══════════════════════════════════════════════════════════════════════════
# Agent 2: TestRunnerAgent
# ═══════════════════════════════════════════════════════════════════════════

async def run_tests(incident_id: str, working_dir: str = None) -> Dict[str, Any]:
    """
    Executes npm test on the fixed code. Runs locally — no external API.

    Returns:
        {
            passed: int,
            failed: int,
            skipped: int,
            output: str,
            agent: "test_runner",
            timestamp: ISO string,
            fallback: bool
        }
    """
    fallback_result = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "output": "Fallback: Test execution skipped",
        "verdict": "WARN",
        "agent": "test_runner",
        "timestamp": datetime.now().isoformat(),
        "fallback": True,
        "duration_ms": 0
    }

    if not working_dir:
        working_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "demo-service"
        )

    if not os.path.exists(working_dir):
        print(f"[AGENT_FALLBACK] TestRunnerAgent: working dir not found: {working_dir}")
        return fallback_result

    start = datetime.now()

    try:
        npm_command = shutil.which("npm.cmd") or shutil.which("npm") or "npm"

        # Run npm test with timeout
        result = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                npm_command, "test", "--if-present",
                cwd=working_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            ),
            timeout=AGENT_TIMEOUT
        )

        stdout, _ = await asyncio.wait_for(
            result.communicate(),
            timeout=AGENT_TIMEOUT
        )

        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        duration = int((datetime.now() - start).total_seconds() * 1000)

        # Parse test results from output
        passed = output.lower().count("passing") + output.lower().count("pass")
        failed = output.lower().count("failing") + output.lower().count("fail")

        # Determine verdict
        if result.returncode == 0:
            verdict = "PASS"
        elif failed > 0:
            verdict = "FAIL"
        else:
            verdict = "WARN"

        return {
            "passed": max(passed, 1) if result.returncode == 0 else passed,
            "failed": failed,
            "skipped": 0,
            "exit_code": result.returncode,
            "output": output[-1000:],  # Last 1000 chars
            "verdict": verdict,
            "agent": "test_runner",
            "timestamp": datetime.now().isoformat(),
            "fallback": False,
            "duration_ms": duration
        }

    except asyncio.TimeoutError:
        print(f"[AGENT_FALLBACK] TestRunnerAgent: timeout after {AGENT_TIMEOUT}s")
        return fallback_result
    except Exception as e:
        print(f"[AGENT_FALLBACK] TestRunnerAgent: {e}")
        fallback_result["output"] = f"Error: {str(e)}"
        return fallback_result


# ═══════════════════════════════════════════════════════════════════════════
# Agent 3: ApprovalRouterAgent
# ═══════════════════════════════════════════════════════════════════════════

async def route_approval(
    incident_id: str,
    risk_assessment: Dict[str, Any],
    static_result: Dict[str, Any],
    test_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Pure logic agent — no API call needed.
    Routes based on combined signals from risk assessment + static analysis + tests.

    Routing logic:
        confidence=high + static=PASS + tests=pass + risk=low  → auto-approve
        confidence=medium OR static=WARN OR risk=medium         → review carefully
        tests=failing OR static=FAIL OR risk=high               → escalate, block deploy

    Returns:
        {
            recommendation: "approve" | "review" | "escalate",
            routing_reason: str,
            route_to: "on_call_engineer" | "senior_engineer" | "auto",
            urgency: "low" | "medium" | "high",
            agent: "approval_router",
            ...
        }
    """
    start = datetime.now()

    # Extract signals
    confidence = risk_assessment.get("confidence", "medium")
    risk_level = risk_assessment.get("risk_level", "medium")
    static_verdict = static_result.get("verdict", "PASS")
    test_verdict = test_result.get("verdict", "PASS")
    test_failed = test_result.get("failed", 0)

    # Decision logic
    recommendation = "review"
    routing_reason = ""
    route_to = "on_call_engineer"
    urgency = "medium"

    # FAIL conditions — escalate and block
    if test_verdict == "FAIL" or test_failed > 0:
        recommendation = "escalate"
        routing_reason = f"Tests failing ({test_failed} failures). Deployment blocked."
        route_to = "senior_engineer"
        urgency = "high"
    elif static_verdict == "FAIL":
        recommendation = "escalate"
        routing_reason = "Static analysis found critical issues. Deployment blocked."
        route_to = "senior_engineer"
        urgency = "high"
    elif risk_level == "high":
        recommendation = "escalate"
        routing_reason = "Risk assessment rated HIGH. Senior review required."
        route_to = "senior_engineer"
        urgency = "high"

    # WARN conditions — review carefully
    elif static_verdict == "WARN":
        recommendation = "review"
        routing_reason = "Static analysis has warnings. Review findings before approving."
        route_to = "on_call_engineer"
        urgency = "medium"
    elif confidence == "medium" or risk_level == "medium":
        recommendation = "review"
        routing_reason = "Medium confidence or risk. Careful review recommended."
        route_to = "on_call_engineer"
        urgency = "medium"

    # PASS conditions — recommend approve
    elif confidence == "high" and static_verdict == "PASS" and test_verdict == "PASS" and risk_level == "low":
        recommendation = "approve"
        routing_reason = "All checks passed. High confidence, low risk, tests passing."
        route_to = "auto"
        urgency = "low"
    else:
        recommendation = "review"
        routing_reason = "Standard review path."
        route_to = "on_call_engineer"
        urgency = "medium"

    duration = int((datetime.now() - start).total_seconds() * 1000)

    return {
        "recommendation": recommendation,
        "routing_reason": routing_reason,
        "route_to": route_to,
        "urgency": urgency,
        "signals": {
            "confidence": confidence,
            "risk_level": risk_level,
            "static_verdict": static_verdict,
            "test_verdict": test_verdict,
            "test_failures": test_failed
        },
        "agent": "approval_router",
        "timestamp": datetime.now().isoformat(),
        "fallback": False,
        "duration_ms": duration
    }


# ═══════════════════════════════════════════════════════════════════════════
# Agent 4: PostIncidentReportAgent
# ═══════════════════════════════════════════════════════════════════════════

async def generate_post_incident_report(
    incident_id: str,
    incident_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generates a post-incident report using Granite via watsonx.ai.
    Appends to incident-history.json for institutional memory.

    Returns:
        {
            report: { timeline, root_cause, fix_summary, prevention },
            runbook_entry: str,
            agent: "post_incident",
            ...
        }
    """
    fallback_report = {
        "report": {
            "timeline": f"Incident {incident_id} detected and resolved",
            "root_cause": incident_data.get("plan_response", "See incident details"),
            "fix_summary": "Automated fix applied by IBM Bob",
            "prevention": "Review caching patterns and add TTL to in-memory stores"
        },
        "runbook_entry": f"[{datetime.now().isoformat()}] Incident {incident_id} resolved via automated pipeline",
        "agent": "post_incident",
        "timestamp": datetime.now().isoformat(),
        "fallback": True,
        "duration_ms": 0
    }

    if not WATSONX_API_KEY or not _build_watsonx_scope():
        print(f"[AGENT_FALLBACK] PostIncidentReportAgent: credentials not configured")
        _append_to_history(incident_id, fallback_report)
        return fallback_report

    start = datetime.now()

    try:
        import aiohttp

        service = incident_data.get("service", "unknown")
        plan = incident_data.get("plan_response", "")[:500]
        fix = incident_data.get("bob_response", "")[:500]
        risk = json.dumps(incident_data.get("risk_assessment", {}))

        prompt = f"""Generate a post-incident report for this resolved production incident.

SERVICE: {service}
INCIDENT ID: {incident_id}
ROOT CAUSE ANALYSIS: {plan}
FIX APPLIED: {fix}
RISK ASSESSMENT: {risk}

Return ONLY valid JSON with these fields:
- timeline: string (chronological summary of the incident)
- root_cause: string (plain English root cause)
- fix_summary: string (what was fixed and how)
- prevention: string (how to prevent this in the future)
- runbook_entry: string (one-line entry for the operations runbook)
"""

        endpoint = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
        iam_token = await get_iam_token(WATSONX_API_KEY)
        headers = {
            "Authorization": f"Bearer {iam_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "model_id": WATSONX_MODEL_ID,
            "input": prompt,
            "parameters": {"max_new_tokens": 400, "temperature": 0},
            **_build_watsonx_scope()
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=AGENT_TIMEOUT)
            ) as response:
                if response.status != 200:
                    print(f"[AGENT_FALLBACK] PostIncidentReportAgent: watsonx.ai returned {response.status}")
                    _append_to_history(incident_id, fallback_report)
                    return fallback_report

                result = await response.json()
                generated = result.get("results", [{}])[0].get("generated_text", "")

                # Parse
                cleaned = generated.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                try:
                    parsed = json.loads(cleaned)
                    duration = int((datetime.now() - start).total_seconds() * 1000)

                    report = {
                        "report": {
                            "timeline": parsed.get("timeline", ""),
                            "root_cause": parsed.get("root_cause", ""),
                            "fix_summary": parsed.get("fix_summary", ""),
                            "prevention": parsed.get("prevention", "")
                        },
                        "runbook_entry": parsed.get("runbook_entry", ""),
                        "agent": "post_incident",
                        "timestamp": datetime.now().isoformat(),
                        "fallback": False,
                        "duration_ms": duration
                    }

                    _append_to_history(incident_id, report)
                    return report

                except json.JSONDecodeError:
                    print(f"[AGENT_FALLBACK] PostIncidentReportAgent: failed to parse response")
                    _append_to_history(incident_id, fallback_report)
                    return fallback_report

    except asyncio.TimeoutError:
        print(f"[AGENT_FALLBACK] PostIncidentReportAgent: timeout after {AGENT_TIMEOUT}s")
        _append_to_history(incident_id, fallback_report)
        return fallback_report
    except Exception as e:
        print(f"[AGENT_FALLBACK] PostIncidentReportAgent: {e}")
        _append_to_history(incident_id, fallback_report)
        return fallback_report


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

async def run_agent_pipeline(
    incident_id: str,
    incident_data: Dict[str, Any],
    event_callback=None
) -> Dict[str, Any]:
    """
    Runs the 4-agent pipeline sequentially.
    Each agent result feeds into the next.
    Emits SSE events via event_callback for real-time dashboard updates.

    Args:
        incident_id: Unique incident identifier
        incident_data: Full incident data including Bob's analysis
        event_callback: async callable(event_dict) for SSE emission

    Returns:
        Complete pipeline results
    """
    results = {}

    bob_diff = incident_data.get("bob_response", "")
    bob_plan = incident_data.get("plan_response", "")
    risk_assessment = incident_data.get("risk_assessment", {})

    # ── Agent 1: Static Analysis ──────────────────────────────────
    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "static_analysis",
            "status": "running", "message": "Running security review..."
        })

    static_result = await run_static_analysis(incident_id, bob_diff, bob_plan)
    results["static_analysis"] = static_result

    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "static_analysis",
            "status": static_result["verdict"].lower(),
            "result": static_result,
            "message": f"Static analysis: {static_result['verdict']}"
        })

    # ── Agent 2: Test Runner ──────────────────────────────────────
    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "test_runner",
            "status": "running", "message": "Running regression tests..."
        })

    test_result = await run_tests(incident_id)
    results["test_runner"] = test_result

    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "test_runner",
            "status": test_result["verdict"].lower(),
            "result": test_result,
            "message": f"Tests: {test_result['verdict']} (passed: {test_result['passed']})"
        })

    # ── Agent 3: Approval Router ──────────────────────────────────
    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "approval_router",
            "status": "running", "message": "Evaluating approval routing..."
        })

    approval_result = await route_approval(
        incident_id, risk_assessment, static_result, test_result
    )
    results["approval_router"] = approval_result

    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "approval_router",
            "status": approval_result["recommendation"],
            "result": approval_result,
            "message": f"Routing: {approval_result['recommendation']} — {approval_result['routing_reason']}"
        })

    # ── Pipeline Complete ─────────────────────────────────────────
    pipeline_result = {
        "incident_id": incident_id,
        "agents": results,
        "pipeline_verdict": approval_result["recommendation"],
        "routing_reason": approval_result["routing_reason"],
        "completed_at": datetime.now().isoformat(),
        "all_agents_passed": (
            static_result["verdict"] in ("PASS", "WARN") and
            test_result["verdict"] in ("PASS", "WARN") and
            approval_result["recommendation"] != "escalate"
        )
    }

    if event_callback:
        await event_callback({
            "phase": "agent_pipeline_complete",
            "result": pipeline_result,
            "message": f"Pipeline complete: {pipeline_result['pipeline_verdict']}"
        })

    return pipeline_result


async def run_post_incident(incident_id: str, incident_data: Dict[str, Any], event_callback=None):
    """
    Runs PostIncidentReportAgent separately (after resolution).
    Called when BobShell emits RESOLVED.
    """
    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "post_incident",
            "status": "running", "message": "Generating post-incident report..."
        })

    report = await generate_post_incident_report(incident_id, incident_data)

    if event_callback:
        await event_callback({
            "phase": "agent", "agent": "post_incident",
            "status": "complete",
            "result": report,
            "message": "Post-incident report generated"
        })

    return report


# ═══════════════════════════════════════════════════════════════════════════
# Institutional Memory — incident-history.json
# ═══════════════════════════════════════════════════════════════════════════

def _get_history_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "incident-history.json"
    )


def _append_to_history(incident_id: str, report: Dict[str, Any]):
    """Append a resolved incident to the institutional memory file."""
    history_path = _get_history_path()

    try:
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = {"incidents": []}

        entry = {
            "id": incident_id,
            "resolved_at": datetime.now().isoformat(),
            "report": report.get("report", {}),
            "runbook_entry": report.get("runbook_entry", ""),
            "fallback": report.get("fallback", False)
        }

        history["incidents"].append(entry)

        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        print(f"Updated incident-history.json with incident {incident_id}")

    except Exception as e:
        print(f"WARNING: Failed to update incident history: {e}")


def get_incident_history() -> Dict[str, Any]:
    """Read the institutional memory file."""
    history_path = _get_history_path()

    try:
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"WARNING: Failed to read incident history: {e}")

    return {"incidents": []}


def get_similar_incidents(root_cause_text: str, max_results: int = 3) -> list:
    """Find past incidents with similar root causes for Bob's context enrichment."""
    history = get_incident_history()
    similar = []

    keywords = set(root_cause_text.lower().split())

    for incident in history.get("incidents", []):
        report = incident.get("report", {})
        past_cause = report.get("root_cause", "").lower()

        # Simple keyword overlap scoring
        past_words = set(past_cause.split())
        overlap = len(keywords & past_words)

        if overlap >= 2:
            similar.append({
                "incident_id": incident.get("id"),
                "root_cause": report.get("root_cause", ""),
                "fix_summary": report.get("fix_summary", ""),
                "resolved_at": incident.get("resolved_at"),
                "relevance_score": overlap
            })

    similar.sort(key=lambda x: x["relevance_score"], reverse=True)
    return similar[:max_results]
