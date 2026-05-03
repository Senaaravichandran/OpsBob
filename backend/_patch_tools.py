"""
Usage: python _patch_tools.py "https://your-domain.com"
Updates all 4 sub-agent tool servers to the given public URL.
"""
import asyncio, os, sys, json
from dotenv import load_dotenv
load_dotenv()
import aiohttp
from iam_auth import get_iam_token

HOST     = os.getenv("ORCHESTRATE_HOST")
INST     = os.getenv("ORCHESTRATE_INSTANCE_ID")
API_KEY  = os.getenv("WATSONX_API_KEY")

# tool_id -> http_path
TOOLS = {
    "81b93d60-16d5-4609-b1f0-1367733c69c6": "/orchestrate/static-analysis",
    "edebdf08-fc86-46ca-8785-b18fbff59ed9": "/orchestrate/run-tests",
    "5327d338-0cd2-42bd-a2bb-1db0f0d019e0": "/orchestrate/route-approval",
    "84d2d23b-67d1-4ab3-b5ab-1434e97864c7": "/orchestrate/post-incident",
}

async def patch(public_url: str):
    token = await get_iam_token(API_KEY)
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base  = f"{HOST}/instances/{INST}/v1/orchestrate"

    async with aiohttp.ClientSession() as s:
        # Fetch current tool definitions
        async with s.get(f"{base}/tools", headers=hdrs) as r:
            tools = await r.json()

        tool_map = {t["id"]: t for t in tools}

        for tool_id, path in TOOLS.items():
            t = tool_map.get(tool_id)
            if not t:
                print(f"  WARN: tool {tool_id} not found")
                continue

            # Patch server URL in the binding
            t["binding"]["openapi"]["servers"] = [public_url]

            async with s.put(f"{base}/tools/{tool_id}", headers=hdrs, json=t) as r:
                status = r.status
                print(f"  [{status}] {path}  ->  {public_url}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python _patch_tools.py https://your-domain.com")
        sys.exit(1)
    url = sys.argv[1].rstrip("/")
    print(f"\nPatching all 4 tool endpoints to: {url}\n")
    asyncio.run(patch(url))
    print("\nDone.")
