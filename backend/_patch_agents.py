"""
Patch all 4 sub-agent instructions and guidelines so they:
- NEVER ask for clarification
- ALWAYS call their tool immediately using the message they receive
- ALWAYS republish to the live environment
"""
import asyncio, os, json
from dotenv import load_dotenv
load_dotenv()
import aiohttp
from iam_auth import get_iam_token

HOST    = os.getenv("ORCHESTRATE_HOST")
INST    = os.getenv("ORCHESTRATE_INSTANCE_ID")
ENV_ID  = os.getenv("ORCHESTRATE_ENV_ID", "5a564980-53bb-479e-b170-c5029e348314")
API_KEY = os.getenv("WATSONX_API_KEY")

AGENTS = {
    "b802246a-8bbe-4f8b-8de1-8121b10ef4f6": {
        "name": "static_analysis_agent",
        "instructions": (
            "You are a pre-deployment static code reviewer. "
            "When you receive ANY message, immediately call the review_code_fix tool using the message field. "
            "Pass the full message as-is to the tool. Do NOT ask for clarification. "
            "Do NOT ask for incident_id or code_diff separately — they are embedded in the message. "
            "Call the tool first, then return its verdict and findings."
        ),
        "guidelines": [
            {
                "display_name": "Always call the tool immediately",
                "condition": "You receive any message",
                "action": "Immediately call review_code_fix with the message. Never ask for more input.",
                "tool": ""
            }
        ]
    },
    "89501f65-87d6-47e7-af82-caae8c9f0742": {
        "name": "test_runner_agent",
        "instructions": (
            "You are a regression test runner. "
            "When you receive ANY message, immediately call the run_regression_tests tool using the message field. "
            "Pass the full message as-is to the tool. Do NOT ask for clarification. "
            "Do NOT ask for incident_id or test_command separately — they are embedded in the message. "
            "Call the tool first, then return its results."
        ),
        "guidelines": [
            {
                "display_name": "Always call the tool immediately",
                "condition": "You receive any message",
                "action": "Immediately call run_regression_tests with the message. Never ask for more input.",
                "tool": ""
            }
        ]
    },
    "a5900533-80f2-49db-b8b6-72e167e709c9": {
        "name": "approval_router_agent",
        "instructions": (
            "You are an approval router for production fixes. "
            "When you receive ANY message, immediately call the route_fix_approval tool using the message field. "
            "Pass the full message as-is to the tool. Do NOT ask for clarification. "
            "Do NOT ask for incident_id or risk_score separately — they are embedded in the message. "
            "Call the tool first, then return its routing decision."
        ),
        "guidelines": [
            {
                "display_name": "Always call the tool immediately",
                "condition": "You receive any message",
                "action": "Immediately call route_fix_approval with the message. Never ask for more input.",
                "tool": ""
            }
        ]
    },
    "682d5d7a-f454-47db-af27-e5459c7350c2": {
        "name": "post_incident_agent",
        "instructions": (
            "You are a post-incident report generator. "
            "When you receive ANY message, immediately call the generate_incident_report tool using the message field. "
            "Pass the full message as-is to the tool. Do NOT ask for clarification. "
            "Do NOT ask for incident_id or timeline separately — they are embedded in the message. "
            "Call the tool first, then return the generated report."
        ),
        "guidelines": [
            {
                "display_name": "Always call the tool immediately",
                "condition": "You receive any message",
                "action": "Immediately call generate_incident_report with the message. Never ask for more input.",
                "tool": ""
            }
        ]
    }
}

async def patch():
    token = await get_iam_token(API_KEY)
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base  = f"{HOST}/instances/{INST}/v1/orchestrate"

    async with aiohttp.ClientSession() as s:
        for agent_id, patch_data in AGENTS.items():
            name = patch_data["name"]

            # Fetch current definition
            async with s.get(f"{base}/agents/{agent_id}", headers=hdrs) as r:
                agent = await r.json()

            # Patch instructions and guidelines
            agent["instructions"] = patch_data["instructions"]
            agent["guidelines"]   = patch_data["guidelines"]

            # Update agent (draft)
            async with s.put(f"{base}/agents/{agent_id}", headers=hdrs, json=agent) as r:
                status = r.status
                if status in (200, 201):
                    print(f"  [OK] Updated instructions for {name}")
                else:
                    body = await r.text()
                    print(f"  [ERR {status}] {name}: {body[:200]}")
                    continue

            # Republish to live environment
            env_id = next(
                (e["id"] for e in agent.get("environments", []) if e["name"] == "live"),
                None
            )
            if env_id:
                publish_url = f"{base}/agents/{agent_id}/environments/{env_id}/publish"
                async with s.post(publish_url, headers=hdrs, json={}) as r:
                    pub_status = r.status
                    if pub_status in (200, 201, 202):
                        print(f"  [OK] Republished {name} to live (env {env_id})")
                    else:
                        body = await r.text()
                        print(f"  [ERR {pub_status}] Publish {name}: {body[:200]}")
            else:
                print(f"  [WARN] No live env found for {name}")

asyncio.run(patch())
print("\nDone.")
