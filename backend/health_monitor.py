"""
System Health Monitor for OpsBob.
Periodically checks all service dependencies and returns health status.
Powers the SystemHealthBar component in the frontend.
"""

import asyncio
import os
import time
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from bob_client import get_bob_command_parts, get_bob_subprocess_env, is_bob_api_key_configured, is_bob_shell_available
from iam_auth import get_iam_token

load_dotenv()

# Service check cache — avoid hammering APIs
_health_cache = {}
_cache_ttl = 30  # seconds


async def check_service_health(service_name: str, check_fn) -> Dict[str, Any]:
    """Check single service health with caching."""
    now = time.time()
    cached = _health_cache.get(service_name)

    if cached and (now - cached["checked_at"]) < _cache_ttl:
        return cached

    try:
        result = await asyncio.wait_for(check_fn(), timeout=5)
        status = {
            "service": service_name,
            "status": "connected",
            "latency_ms": result.get("latency_ms", 0),
            "details": result.get("details", ""),
            "checked_at": now,
            "timestamp": datetime.now().isoformat()
        }
    except asyncio.TimeoutError:
        status = {
            "service": service_name,
            "status": "degraded",
            "latency_ms": 5000,
            "details": "Timeout after 5s",
            "checked_at": now,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        status = {
            "service": service_name,
            "status": "unavailable",
            "latency_ms": 0,
            "details": str(e),
            "checked_at": now,
            "timestamp": datetime.now().isoformat()
        }

    _health_cache[service_name] = status
    return status


async def _check_bob_shell():
    """Check Bob shell availability through PATH or the vendored bundle."""
    if not is_bob_shell_available():
        raise Exception("Bob shell runtime is unavailable")
    if not is_bob_api_key_configured():
        raise Exception("Bob API key is not configured")

    command_parts = get_bob_command_parts()
    executable = command_parts[0] if command_parts else "bob"
    return {
        "latency_ms": 0,
        "details": f"Runtime ready via {os.path.basename(executable)} with API key configured"
    }


async def _check_watsonx_ai():
    """Check watsonx.ai connectivity."""
    import aiohttp
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    key = os.getenv("WATSONX_API_KEY", "")

    if not key:
        raise Exception("WATSONX_API_KEY not configured")

    start = time.time()
    iam_token = await get_iam_token(key)
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{url}/ml/v1/models?version=2023-05-29&limit=1",
            headers={
                "Authorization": f"Bearer {iam_token}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status >= 400:
                raise Exception(f"HTTP {resp.status}")
            latency = int((time.time() - start) * 1000)
            return {
                "latency_ms": latency,
                "details": f"HTTP {resp.status}"
            }


async def _check_orchestrate():
    """Check watsonx Orchestrate connectivity via the agents list endpoint."""
    import aiohttp
    host = os.getenv("ORCHESTRATE_HOST", "")
    instance_id = os.getenv("ORCHESTRATE_INSTANCE_ID", "")
    key = os.getenv("WATSONX_API_KEY", "") or os.getenv("ORCHESTRATE_API_KEY", "")

    if not host or not instance_id or not key:
        raise Exception("ORCHESTRATE credentials not configured")

    start = time.time()
    iam_token = await get_iam_token(key)
    url = f"{host}/instances/{instance_id}/v1/orchestrate/agents"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers={
                "Authorization": f"Bearer {iam_token}",
                "Content-Type": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            latency = int((time.time() - start) * 1000)
            if resp.status >= 400:
                raise Exception(f"HTTP {resp.status} (agents endpoint)")
            return {
                "latency_ms": latency,
                "details": f"HTTP {resp.status} — agents endpoint reachable"
            }


async def _check_instana():
    """Check Instana connectivity."""
    import aiohttp
    url = os.getenv("INSTANA_BASE_URL", "")
    token = os.getenv("INSTANA_API_TOKEN", "")

    if not url or "your-tenant" in url:
        # Using local fallback — demo service endpoints
        return {
            "latency_ms": 0,
            "details": "Using local demo service (Instana trial bypassed)"
        }

    start = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{url}/api/v1/instana/health",
            headers={"Authorization": f"apiToken {token}"},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            latency = int((time.time() - start) * 1000)
            return {
                "latency_ms": latency,
                "details": f"HTTP {resp.status}"
            }


async def _check_demo_service():
    """Check demo service health."""
    import aiohttp
    demo_url = os.getenv("DEMO_SERVICE_URL", "http://localhost:3001")

    start = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{demo_url}/health",
            timeout=aiohttp.ClientTimeout(total=3)
        ) as resp:
            if resp.status >= 400:
                raise Exception(f"HTTP {resp.status}")
            latency = int((time.time() - start) * 1000)
            data = await resp.json()
            return {
                "latency_ms": latency,
                "details": f"Heap: {data.get('memory', {}).get('heapUsed', '?')} | Cache: {data.get('cacheSize', '?')}"
            }


async def get_all_service_health() -> Dict[str, Any]:
    """
    Check health of all IBM services.
    Returns structured health status for the SystemHealthBar component.
    """
    services = {
        "bob_shell": _check_bob_shell,
        "watsonx_ai": _check_watsonx_ai,
        "orchestrate": _check_orchestrate,
        "instana": _check_instana,
        "demo_service": _check_demo_service
    }

    results = {}
    for name, check_fn in services.items():
        results[name] = await check_service_health(name, check_fn)

    # Overall system status
    statuses = [r["status"] for r in results.values()]
    if all(s == "connected" for s in statuses):
        overall = "nominal"
    elif any(s == "unavailable" for s in statuses):
        overall = "degraded"
    else:
        overall = "partial"

    return {
        "overall": overall,
        "services": results,
        "timestamp": datetime.now().isoformat()
    }
