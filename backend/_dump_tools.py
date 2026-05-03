"""Dump current tool definitions from Orchestrate to understand schema structure."""
import asyncio, os, sys, json
from dotenv import load_dotenv
load_dotenv()
import aiohttp
from iam_auth import get_iam_token

HOST    = os.getenv("ORCHESTRATE_HOST")
INST    = os.getenv("ORCHESTRATE_INSTANCE_ID")
API_KEY = os.getenv("WATSONX_API_KEY")

TOOL_IDS = [
    "81b93d60-16d5-4609-b1f0-1367733c69c6",  # static-analysis
    "edebdf08-fc86-46ca-8785-b18fbff59ed9",  # run-tests
    "5327d338-0cd2-42bd-a2bb-1db0f0d019e0",  # route-approval
    "84d2d23b-67d1-4ab3-b5ab-1434e97864c7",  # post-incident
]

async def dump():
    token = await get_iam_token(API_KEY)
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base  = f"{HOST}/instances/{INST}/v1/orchestrate"

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base}/tools", headers=hdrs) as r:
            tools = await r.json()

    for t in tools:
        if t["id"] in TOOL_IDS:
            print(f"\n{'='*60}")
            print(f"TOOL: {t.get('name')} ({t['id']})")
            print(f"{'='*60}")
            print(json.dumps(t, indent=2))
            break  # just print the first one to understand structure

asyncio.run(dump())
