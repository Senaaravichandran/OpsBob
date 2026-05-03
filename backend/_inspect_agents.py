"""Inspect all 4 sub-agent instructions and guidelines."""
import asyncio, os, json
from dotenv import load_dotenv
load_dotenv()
import aiohttp
from iam_auth import get_iam_token

HOST = os.getenv("ORCHESTRATE_HOST")
INST = os.getenv("ORCHESTRATE_INSTANCE_ID")
API_KEY = os.getenv("WATSONX_API_KEY")

AGENTS = {
    "b802246a-8bbe-4f8b-8de1-8121b10ef4f6": "static_analysis_agent",
    "89501f65-87d6-47e7-af82-caae8c9f0742": "test_runner_agent",
    "a5900533-80f2-49db-b8b6-72e167e709c9": "approval_router_agent",
    "682d5d7a-f454-47db-af27-e5459c7350c2": "post_incident_agent",
}

async def main():
    token = await get_iam_token(API_KEY)
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = f"{HOST}/instances/{INST}/v1/orchestrate"
    async with aiohttp.ClientSession() as s:
        for agent_id, name in AGENTS.items():
            async with s.get(f"{base}/agents/{agent_id}", headers=hdrs) as r:
                data = await r.json()
                print(f"=== {name} ===")
                print("instructions:", data.get("instructions","")[:300])
                print("guidelines:")
                for g in data.get("guidelines", []):
                    print(f"  condition: {g['condition']}")
                    print(f"  action: {g['action']}")
                print()

asyncio.run(main())
