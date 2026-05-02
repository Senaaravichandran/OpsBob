"""
Incident Intelligence — Pattern recognition and context enrichment for OpsBob.

Reads incident-history.json to find similar past incidents and enriches
Bob's prompt with institutional memory. This helps Bob:
  1. Identify recurring patterns faster
  2. Apply proven fix strategies
  3. Build confidence from prior resolutions
"""

import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime


def _get_history_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "incident-history.json"
    )


def load_incident_history() -> List[Dict[str, Any]]:
    """Load all past incidents from institutional memory."""
    history_path = _get_history_path()
    try:
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("incidents", [])
    except Exception as e:
        print(f"WARNING: Failed to load incident history: {e}")
    return []


def find_similar_incidents(
    incident_type: str,
    service: str,
    max_results: int = 3
) -> List[Dict[str, Any]]:
    """
    Find past incidents affecting the same service or incident type.
    Uses keyword matching for similarity scoring.
    """
    history = load_incident_history()
    scored = []

    type_keywords = set(incident_type.lower().replace("_", " ").split())

    for past in history:
        report = past.get("report", {})
        past_cause = report.get("root_cause", "").lower()
        past_fix = report.get("fix_summary", "").lower()

        score = 0

        # Exact service match is strongest signal
        if service.lower() in str(past).lower():
            score += 5

        # Type keyword overlap
        past_words = set(past_cause.split() + past_fix.split())
        overlap = len(type_keywords & past_words)
        score += overlap * 2

        # Common patterns
        if "memory" in past_cause and "memory" in incident_type.lower():
            score += 3
        if "cache" in past_cause and "cache" in incident_type.lower():
            score += 3
        if "leak" in past_cause and "leak" in incident_type.lower():
            score += 3

        if score > 0:
            scored.append({
                **past,
                "relevance_score": score
            })

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:max_results]


def build_context_enrichment(
    incident_type: str,
    service: str
) -> Optional[str]:
    """
    Build an enrichment string to add to Bob's analysis prompt.
    Returns None if no relevant history exists.
    """
    similar = find_similar_incidents(incident_type, service)

    if not similar:
        return None

    sections = []
    sections.append(f"\n--- INSTITUTIONAL MEMORY ({len(similar)} similar past incident(s)) ---")

    for i, past in enumerate(similar, 1):
        report = past.get("report", {})
        sections.append(f"""
Past Incident #{i}: {past.get('id', 'unknown')}
  Resolved: {past.get('resolved_at', 'unknown')}
  Root Cause: {report.get('root_cause', 'N/A')}
  Fix Applied: {report.get('fix_summary', 'N/A')}
  Prevention: {report.get('prevention', 'N/A')}""")

    sections.append("""
--- END INSTITUTIONAL MEMORY ---
Use this past context to inform your analysis, but verify the current issue independently.
""")

    return "\n".join(sections)


def get_stats() -> Dict[str, Any]:
    """Get statistics about the institutional memory."""
    history = load_incident_history()

    if not history:
        return {
            "total_incidents": 0,
            "services_affected": [],
            "avg_resolution_time": "N/A",
            "last_incident": None
        }

    services = set()
    for incident in history:
        # Extract service from report text
        report_text = json.dumps(incident.get("report", {}))
        if "payments-api" in report_text:
            services.add("payments-api")

    return {
        "total_incidents": len(history),
        "services_affected": list(services),
        "last_incident": history[-1].get("resolved_at") if history else None,
        "has_memory": len(history) > 0
    }
