"""
watsonx Orchestrate Client — Programmatic server-side agent invocation

Uses the Orchestrate REST API (/api/v1/orchestrate/runs) to invoke the
incident commander agent.  The commander orchestrates all 4 specialist
agents by calling the backend tool endpoints (/orchestrate/*) internally,
then returns a structured decision.

Pre-incident:  incident context → commander → static-analysis + run-tests + route-approval
Post-incident: resolution data → commander → post-incident-report

The IAM token is reused from the existing iam_auth module.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
from dotenv import load_dotenv

from iam_auth import get_iam_token

load_dotenv()

WATSONX_API_KEY         = os.getenv("WATSONX_API_KEY")
ORCHESTRATE_HOST        = os.getenv("ORCHESTRATE_HOST", "https://us-south.watson-orchestrate.cloud.ibm.com")
ORCHESTRATE_INSTANCE_ID = os.getenv("ORCHESTRATE_INSTANCE_ID", "12e43571-ef61-4ba1-ab1c-33db7d1bcef0")
ORCHESTRATE_AGENT_ID    = os.getenv("ORCHESTRATE_AGENT_ID", "682d5d7a-f454-47db-af27-e5459c7350c2")
ORCHESTRATE_ENV_ID      = os.getenv("ORCHESTRATE_ENV_ID", "891f6e96-3953-4372-8852-1caecb48b7fa")
BACKEND_URL             = os.getenv("BACKEND_URL", "http://localhost:8000")

# Orchestrate API base — the REST endpoint lives at /api/v1/orchestrate/...
_API_BASE = f"{ORCHESTRATE_HOST}/instances/{ORCHESTRATE_INSTANCE_ID}/api/v1/orchestrate"

# Orchestrate API timeout — generous because agents call our backend endpoints
_RUN_TIMEOUT = 60  # 60s for a single run call


# ── Token helper ─────────────────────────────────────────────────────────────

async def _auth_headers() -> Dict[str, str]:
    if not WATSONX_API_KEY:
        raise RuntimeError("WATSONX_API_KEY not configured — cannot call Orchestrate API")
    token = await get_iam_token(WATSONX_API_KEY)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Runs-based API ────────────────────────────────────────────────────────────

async def _invoke_agent(message_text: str, thread_id: str = "") -> Dict[str, Any]:
    """
    Send a message to the Orchestrate agent via POST /api/v1/orchestrate/runs.

    Returns the full API response dict and the thread_id for follow-ups.
    """
    url = f"{_API_BASE}/runs"
    hdrs = await _auth_headers()
    payload = {
        "agent_id": ORCHESTRATE_AGENT_ID,
        "message": {
            "role": "user",
            "content": message_text,
        },
    }
    if thread_id:
        payload["thread_id"] = thread_id
    if ORCHESTRATE_ENV_ID:
        payload["environment_id"] = ORCHESTRATE_ENV_ID

    async with aiohttp.ClientSession() as http:
        async with http.post(
            url, headers=hdrs, json=payload,
            timeout=aiohttp.ClientTimeout(total=_RUN_TIMEOUT),
        ) as resp:
            body = await resp.text()
            if resp.status not in (200, 201):
                raise RuntimeError(
                    f"Orchestrate runs failed: HTTP {resp.status} — {body[:300]}"
                )
            data = json.loads(body)
            return data


# ── Decision parsing ──────────────────────────────────────────────────────────

def _extract_text(response: Dict[str, Any]) -> str:
    """Pull agent text from wherever the Orchestrate API puts it."""
    # New API returns message.content or output.text
    msg = response.get("message") or {}
    if isinstance(msg, dict):
        content = msg.get("content")
        if content:
            return content

    return (
        (response.get("output") or {}).get("text")
        or response.get("response")
        or response.get("result")
        or json.dumps(response)
    )


def _extract_thread_id(response: Dict[str, Any]) -> str:
    """Extract thread_id from the response for follow-up calls."""
    return response.get("thread_id", "")


def _parse_decision(text: str) -> str:
    """
    Read the agent's text response and return one of:
      "approve" | "escalate" | "reject" | "review"
    """
    t = text.lower()
    # Check explicit keywords — most specific first
    if any(k in t for k in ("auto-approve", "auto approve", "automatically approve")):
        return "approve"
    if "approve" in t and "not approve" not in t and "cannot approve" not in t:
        return "approve"
    if any(k in t for k in ("escalate", "block deploy", "block the deploy", "failing tests", "critical issue")):
        return "escalate"
    if "reject" in t:
        return "reject"
    return "review"


# ── Local fallback pipeline ──────────────────────────────────────────────────

async def _run_local_fallback_pre(
    incident_id: str,
    incident_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    When Orchestrate is unreachable, run the 4-agent pipeline locally
    and derive a decision from the approval_router result.
    """
    from orchestrate_agents import run_agent_pipeline

    pipeline = await run_agent_pipeline(incident_id, incident_data)
    verdict = pipeline.get("pipeline_verdict", "review")

    return {
        "decision": verdict,
        "raw_response": f"Local pipeline verdict: {verdict} — {pipeline.get('routing_reason', '')}",
        "orchestrate_used": False,
        "error": None,
    }


# ── Public API ────────────────────────────────────────────────────────────────

async def run_pre_incident_pipeline(
    incident_id: str,
    incident_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Invoke the incident commander agent with the full incident context.
    Falls back to local pipeline if Orchestrate is unreachable.

    Returns:
      {
        session_id / thread_id: str,
        decision: "approve" | "escalate" | "reject" | "review",
        raw_response: str,
        orchestrate_used: bool,
        error: str | None
      }
    """
    if not WATSONX_API_KEY:
        return {
            "decision": "review",
            "orchestrate_used": False,
            "error": "WATSONX_API_KEY not configured",
        }

    service  = incident_data.get("service", "unknown")
    severity = incident_data.get("severity", "HIGH")
    plan     = (incident_data.get("plan_response") or "")[:800]
    diff     = (incident_data.get("bob_response") or "")[:800]
    risk     = json.dumps(incident_data.get("risk_assessment") or {})

    message = f"""INCIDENT: {incident_id}
SERVICE: {service}
SEVERITY: {severity}

ROOT CAUSE ANALYSIS:
{plan}

PROPOSED CODE FIX (diff):
{diff}

RISK ASSESSMENT:
{risk}

Backend API base URL: {BACKEND_URL}

Please run the full pre-incident verification pipeline:
1. POST {BACKEND_URL}/orchestrate/static-analysis   (incident_id, code_diff, plan_text)
2. POST {BACKEND_URL}/orchestrate/run-tests          (incident_id)
3. POST {BACKEND_URL}/orchestrate/route-approval     (incident_id, risk_assessment, static_result, test_results)

After all three agents complete, return your final decision:
- "approve"   — all checks pass, auto-deploy to production
- "escalate"  — critical issue found, block deployment, notify senior engineer
- "reject"    — fix is incorrect or dangerous
- "review"    — medium confidence, manual review required"""

    try:
        response = await _invoke_agent(message)
        raw = _extract_text(response)
        decision = _parse_decision(raw)
        thread_id = _extract_thread_id(response)

        print(f"[ORCHESTRATE] Pre-incident decision for {incident_id}: {decision}")
        return {
            "session_id": thread_id,
            "decision": decision,
            "raw_response": raw,
            "orchestrate_used": True,
            "error": None,
        }

    except Exception as exc:
        print(f"[ORCHESTRATE] Pre-incident pipeline error for {incident_id}: {exc}")
        print(f"[ORCHESTRATE] Falling back to local pipeline")
        try:
            return await _run_local_fallback_pre(incident_id, incident_data)
        except Exception as fallback_exc:
            print(f"[ORCHESTRATE] Local fallback also failed: {fallback_exc}")
            return {
                "decision": "review",
                "orchestrate_used": False,
                "error": f"Orchestrate: {exc} | Local fallback: {fallback_exc}",
            }


async def run_post_incident_pipeline(
    incident_id: str,
    resolution_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Invoke the incident commander for post-incident reporting after a successful deploy.
    Falls back to local PostIncidentReportAgent.

    Returns:
      {
        session_id / thread_id: str,
        report: str,
        agent: "orchestrate_post_incident",
        orchestrate_used: bool,
        timestamp: ISO str,
        error: str | None
      }
    """
    if not WATSONX_API_KEY:
        return {
            "report": "Post-incident report skipped: WATSONX_API_KEY not configured",
            "agent": "orchestrate_post_incident",
            "orchestrate_used": False,
            "timestamp": datetime.now().isoformat(),
            "error": "WATSONX_API_KEY not configured",
        }

    service     = resolution_data.get("service", "unknown")
    resolved_at = resolution_data.get("resolved_at", datetime.now().isoformat())
    plan        = (resolution_data.get("plan_response") or "")[:500]
    fix         = (resolution_data.get("bob_response") or "")[:400]

    message = f"""INCIDENT RESOLVED: {incident_id}
SERVICE: {service}
RESOLVED AT: {resolved_at}

ROOT CAUSE: {plan}
FIX APPLIED: {fix}

Backend API base URL: {BACKEND_URL}

Please generate a complete post-incident report by calling:
  POST {BACKEND_URL}/orchestrate/post-incident
  Body: {{ "incident_id": "{incident_id}", "resolution_data": <resolution details> }}

Return the structured report including:
- Timeline of events
- Root cause analysis
- Fix summary
- Prevention recommendations
- Runbook entry for future reference"""

    try:
        response = await _invoke_agent(message)
        raw = _extract_text(response)
        thread_id = _extract_thread_id(response)

        print(f"[ORCHESTRATE] Post-incident report generated for {incident_id}")
        return {
            "session_id": thread_id,
            "report": raw,
            "agent": "orchestrate_post_incident",
            "orchestrate_used": True,
            "timestamp": datetime.now().isoformat(),
            "error": None,
        }

    except Exception as exc:
        print(f"[ORCHESTRATE] Post-incident pipeline error for {incident_id}: {exc}")
        # Fall back to local post-incident agent
        from orchestrate_agents import run_post_incident
        try:
            local_report = await run_post_incident(incident_id, resolution_data)
            return {
                "report": local_report.get("report", {}),
                "agent": "orchestrate_post_incident",
                "orchestrate_used": False,
                "timestamp": datetime.now().isoformat(),
                "error": f"Orchestrate unavailable, used local agent: {exc}",
            }
        except Exception as fallback_exc:
            return {
                "report": f"Post-incident report generation failed: {exc}",
                "agent": "orchestrate_post_incident",
                "orchestrate_used": False,
                "timestamp": datetime.now().isoformat(),
                "error": str(fallback_exc),
            }


def is_orchestrate_configured() -> bool:
    """Returns True if the Orchestrate client has enough config to attempt a call."""
    return bool(WATSONX_API_KEY and ORCHESTRATE_INSTANCE_ID and ORCHESTRATE_AGENT_ID)
