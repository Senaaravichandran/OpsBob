"""
Patch all 4 tool schemas in Orchestrate:
- Clear required[] so no fields are mandatory
- Add message: string field so LLM can pass natural language context
"""
import asyncio, os, sys, json
from dotenv import load_dotenv
load_dotenv()
import aiohttp
from iam_auth import get_iam_token

HOST    = os.getenv("ORCHESTRATE_HOST")
INST    = os.getenv("ORCHESTRATE_INSTANCE_ID")
API_KEY = os.getenv("WATSONX_API_KEY")

# tool_id -> friendly name
TOOLS = {
    "81b93d60-16d5-4609-b1f0-1367733c69c6": "static-analysis",
    "edebdf08-fc86-46ca-8785-b18fbff59ed9": "run-tests",
    "5327d338-0cd2-42bd-a2bb-1db0f0d019e0": "route-approval",
    "84d2d23b-67d1-4ab3-b5ab-1434e97864c7": "post-incident",
}

MESSAGE_PROP = {
    "type": "string",
    "title": "Message",
    "description": "Natural language input describing the incident, diff, and context for this agent to process."
}

# Only require 'message' — the LLM will pass the full natural language context.
# Backend models are all-Optional so everything else is extracted server-side.
REQUIRED_BY_TOOL = {
    "81b93d60-16d5-4609-b1f0-1367733c69c6": ["message"],   # static-analysis
    "edebdf08-fc86-46ca-8785-b18fbff59ed9": ["message"],   # run-tests
    "5327d338-0cd2-42bd-a2bb-1db0f0d019e0": ["message"],   # route-approval
    "84d2d23b-67d1-4ab3-b5ab-1434e97864c7": ["message"],   # post-incident
}

async def patch_schemas():
    token = await get_iam_token(API_KEY)
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base  = f"{HOST}/instances/{INST}/v1/orchestrate"

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/tools", headers=hdrs) as r:
            tools = await r.json()

        tool_map = {t["id"]: t for t in tools}

        for tool_id, name in TOOLS.items():
            t = tool_map.get(tool_id)
            if not t:
                print(f"  WARN: tool {tool_id} ({name}) not found")
                continue

            # Patch the __requestBody__ schema
            rb = t.get("input_schema", {}).get("properties", {}).get("__requestBody__", {})
            if rb:
                # Add message field if not already present
                rb.setdefault("properties", {})["message"] = MESSAGE_PROP
                # Restore original required fields — these tell LLM what to populate
                rb["required"] = REQUIRED_BY_TOOL.get(tool_id, [])
                print(f"  Patched schema for {name}: required={rb['required']}, +message field")
            else:
                print(f"  WARN: no __requestBody__ found for {name}")

            async with s.put(f"{base}/tools/{tool_id}", headers=hdrs, json=t) as r:
                status = r.status
                body = await r.text()
                if status in (200, 201):
                    print(f"  [{status}] Updated {name}")
                else:
                    print(f"  [{status}] ERROR for {name}: {body[:200]}")

asyncio.run(patch_schemas())
print("\nDone. All tool schemas updated.")
