"""
Quick diagnostic: list agents + test commander run with correct API path.
Run: python test_orchestrate.py
"""
import asyncio
import aiohttp
import json
import os
from dotenv import load_dotenv
from iam_auth import get_iam_token

load_dotenv()

WATSONX_API_KEY = os.getenv("WATSONX_API_KEY")
ORCHESTRATE_INSTANCE_ID = os.getenv("ORCHESTRATE_INSTANCE_ID")
OLD_AGENT_ID = os.getenv("ORCHESTRATE_AGENT_ID")
OLD_ENV_ID = os.getenv("ORCHESTRATE_ENV_ID")

# From the chat widget script — the LIVE agent
NEW_AGENT_ID = "1c3fde20-54b1-4448-a8c2-2bc4f9fff376"
NEW_ENV_ID = "5a564980-53bb-479e-b170-c5029e348314"

# Correct API host (has api. prefix — distinct from the UI host)
API_HOST = "https://api.us-south.watson-orchestrate.cloud.ibm.com"


async def main():
    token = await get_iam_token(WATSONX_API_KEY)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    base = f"{API_HOST}/instances/{ORCHESTRATE_INSTANCE_ID}/v1/orchestrate"

    # ── 1. List agents ──────────────────────────────────────────────
    print("=" * 60)
    print("AGENTS IN YOUR INSTANCE")
    print("=" * 60)
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"{base}/agents", headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            agents = await r.json()
            for a in agents:
                aid = a.get("id", "?")
                name = a.get("name", "?")
                desc = a.get("description", "")[:80]
                match_old = "  <-- OLD (in .env)" if aid == OLD_AGENT_ID else ""
                match_new = "  <-- NEW (from widget)" if aid == NEW_AGENT_ID else ""
                print(f"  id:   {aid}{match_old}{match_new}")
                print(f"  name: {name}")
                if desc:
                    print(f"  desc: {desc}")
                print()

    # ── 2. Test OLD agent ID ────────────────────────────────────────
    print("=" * 60)
    print(f"TEST OLD agent ID: {OLD_AGENT_ID}")
    print("=" * 60)
    await _run_test(base, headers, OLD_AGENT_ID, OLD_ENV_ID)

    # ── 3. Test NEW agent ID ────────────────────────────────────────
    print("=" * 60)
    print(f"TEST NEW agent ID: {NEW_AGENT_ID}")
    print("=" * 60)
    await _run_test(base, headers, NEW_AGENT_ID, NEW_ENV_ID)


async def _run_test(base, headers, agent_id, env_id):
    payload = {
        "agent_id": agent_id,
        "message": {"role": "user", "content": "Hello, say OK if you are working"},
        "environment_id": env_id,
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{base}/runs",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=40),
        ) as r:
            body = await r.text()
            print(f"HTTP {r.status}")
            try:
                data = json.loads(body)
                print(json.dumps(data, indent=2)[:800])
            except Exception:
                print(body[:400])
    print()


async def test_commander_poll():
    """Start a run against the COMMANDER and poll until completed — shows real response."""
    token = await get_iam_token(WATSONX_API_KEY)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    base = f"{API_HOST}/instances/{ORCHESTRATE_INSTANCE_ID}/v1/orchestrate"

    print("=" * 60)
    print(f"POLLING TEST — COMMANDER: {NEW_AGENT_ID}")
    print("=" * 60)

    payload = {
        "agent_id": NEW_AGENT_ID,
        "message": {"role": "user", "content": "Hello, say OK if you are working"},
        "environment_id": NEW_ENV_ID,
    }

    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{base}/runs",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            run = await r.json()
            run_id = run.get("run_id")
            print(f"Run started: {run_id}")

        # Poll up to 10 x 5s = 50s
        for i in range(10):
            await asyncio.sleep(5)
            async with s.get(
                f"{base}/runs/{run_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
                state = data.get("status", "?")
                print(f"Poll {i+1}: HTTP {r.status} | status={state}")
                if state in ("completed", "failed", "error"):
                    print("Final response:")
                    print(json.dumps(data, indent=2)[:1200])
                    return
        print("Timed out waiting for completion")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "poll":
        asyncio.run(test_commander_poll())
    else:
        asyncio.run(main())
