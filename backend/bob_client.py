"""
Bob API Client - Real IBM Bob API Integration Only
Streams responses as Server-Sent Events for real-time dashboard updates
"""

import os
import json
import aiohttp
from typing import AsyncGenerator, Dict, Any
from dotenv import load_dotenv
from watsonx_client import call_watsonx_risk_assessment

# Load environment variables
load_dotenv()

# Bob API configuration
BOB_API_KEY = os.getenv("BOB_API_KEY")
BOB_API_URL = "https://api.bob.ibm.com/v1/generate"


async def call_bob_orchestrator(context: str) -> AsyncGenerator[str, None]:
    """
    Orchestrates multi-phase Bob API calls for incident analysis
    
    Makes THREE sequential real API calls to IBM Bob:
    1. ASK - Read and understand the code
    2. PLAN - Identify root cause and propose fix
    3. CODE - Generate actual code fix and test
    
    Args:
        context: Pre-assembled context string with incident details and source code
    
    Yields SSE-formatted events for real-time streaming
    """
    
    # Validate API key
    if not BOB_API_KEY or BOB_API_KEY == "your_bob_key_here":
        error_msg = "Bob API key not configured. Set BOB_API_KEY in .env file"
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"
        return
    
    # Conversation history for context
    messages = []
    
    try:
        # ===== PHASE 1: ASK - Code Reading =====
        yield f"data: {json.dumps({'phase': 'ask', 'content': '', 'done': False})}\n\n"
        
        ask_message = {
            "role": "user",
            "content": f"""You are a senior SRE at IBM. A production incident has occurred.

{context}

Read this code carefully. Identify all memory management patterns, object lifecycle issues, and any data structures that could grow without bound. Summarize what you see in 3-4 sentences."""
        }
        
        messages.append(ask_message)
        ask_response = await _call_bob_api(messages)
        
        yield f"data: {json.dumps({'phase': 'ask', 'content': ask_response, 'done': True})}\n\n"
        
        # Add assistant response to conversation
        messages.append({"role": "assistant", "content": ask_response})
        
        # ===== PHASE 2: PLAN - Root Cause Analysis =====
        yield f"data: {json.dumps({'phase': 'plan', 'content': '', 'done': False})}\n\n"
        
        plan_message = {
            "role": "user",
            "content": """Based on your code reading, identify the EXACT root cause of this memory leak. Name the specific variable and line number. Then provide your fix plan in exactly 3 bullet points. Be precise and technical."""
        }
        
        messages.append(plan_message)
        plan_response = await _call_bob_api(messages)
        
        # Call watsonx.ai for risk assessment
        print("Calling watsonx.ai for risk assessment...")
        risk_assessment = await call_watsonx_risk_assessment(plan_response)
        print(f"Risk assessment: {risk_assessment}")
        
        # Yield plan completion with risk assessment
        yield f"data: {json.dumps({
            'phase': 'plan',
            'content': plan_response,
            'risk_assessment': risk_assessment,
            'done': True
        })}\n\n"
        
        # Add assistant response to conversation
        messages.append({"role": "assistant", "content": plan_response})
        
        # ===== PHASE 3: CODE - Generate Fix =====
        yield f"data: {json.dumps({'phase': 'code', 'content': '', 'done': False})}\n\n"
        
        code_message = {
            "role": "user",
            "content": """Now write the code fix. Format as a unified diff:
Lines removed start with -
Lines added start with +
Context lines have no prefix

Then write one unit test that would catch this regression. Keep it minimal and surgical."""
        }
        
        messages.append(code_message)
        code_response = await _call_bob_api(messages)
        
        yield f"data: {json.dumps({'phase': 'code', 'content': code_response, 'done': True})}\n\n"
        
        # ===== COMPLETE =====
        yield f"data: {json.dumps({'phase': 'complete', 'content': '', 'done': True})}\n\n"
        
    except aiohttp.ClientError as e:
        error_msg = f"Bob API connection error: {str(e)}"
        print(f"ERROR: {error_msg}")
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"
    
    except Exception as e:
        error_msg = f"Bob API error: {str(e)}"
        print(f"ERROR: {error_msg}")
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"


async def _call_bob_api(messages: list) -> str:
    """
    Makes a single call to IBM Bob API
    Returns the generated response text
    Raises exception on error
    """
    headers = {
        "Authorization": f"Bearer {BOB_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "bob-orchestrator",
        "messages": messages,
        "max_tokens": 500
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            BOB_API_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Bob API returned {response.status}: {error_text}")
            
            result = await response.json()
            
            # Extract response text from various possible response formats
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0].get("message", {}).get("content", "")
            elif "text" in result:
                return result["text"]
            elif "content" in result:
                return result["content"]
            else:
                raise Exception(f"Unexpected Bob API response format: {result}")


# Made with Bob
