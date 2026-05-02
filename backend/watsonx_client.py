"""
watsonx.ai Client - Integration with IBM watsonx.ai and Granite models
Provides risk assessment and text generation capabilities
"""

import os
import json
import aiohttp
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# watsonx.ai configuration
WATSONX_API_KEY = os.getenv("WATSONX_API_KEY")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID")
WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")


async def call_watsonx_risk_assessment(bob_plan_text: str) -> Dict[str, Any]:
    """
    Calls watsonx.ai to assess risk of Bob's proposed fix
    
    Uses IBM Granite model to analyze the fix plan and return structured
    risk assessment including confidence level, blast radius, and recommended action.
    
    Args:
        bob_plan_text: Bob's plan-mode output with root cause and fix proposal
    
    Returns:
        Dictionary with risk assessment fields:
        - confidence: "high", "medium", or "low"
        - risk_level: "high", "medium", or "low"
        - estimated_blast_radius: Description of potential impact
        - recommended_action: "approve", "escalate", or "reject"
        - reasoning: One sentence explanation
    """
    
    # Fallback response if watsonx.ai is unavailable
    fallback_response = {
        "confidence": "medium",
        "risk_level": "medium",
        "estimated_blast_radius": "Unknown - watsonx.ai unavailable",
        "recommended_action": "escalate",
        "reasoning": "watsonx.ai unavailable, manual review recommended"
    }
    
    # Validate configuration
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        print("WARNING: watsonx.ai credentials not configured, using fallback")
        return fallback_response
    
    try:
        # Construct the API endpoint
        endpoint = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {WATSONX_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Prepare the prompt
        system_prompt = """You are a production risk assessor. Given an AI-generated fix proposal, return ONLY valid JSON with these fields:
confidence (high/medium/low), risk_level (high/medium/low), estimated_blast_radius (string), recommended_action (approve/escalate/reject), reasoning (one sentence max)"""
        
        input_text = f"<system>{system_prompt}</system>\n\nFix proposal: {bob_plan_text}"
        
        # Prepare request payload
        payload = {
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": WATSONX_PROJECT_ID,
            "input": input_text,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0
            }
        }
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"watsonx.ai API error {response.status}: {error_text}")
                    return fallback_response
                
                result = await response.json()
                
                # Extract generated text
                if "results" in result and len(result["results"]) > 0:
                    generated_text = result["results"][0].get("generated_text", "")
                    
                    # Parse JSON from generated text
                    try:
                        # Clean up the text - remove markdown code blocks if present
                        cleaned_text = generated_text.strip()
                        if cleaned_text.startswith("```json"):
                            cleaned_text = cleaned_text[7:]
                        if cleaned_text.startswith("```"):
                            cleaned_text = cleaned_text[3:]
                        if cleaned_text.endswith("```"):
                            cleaned_text = cleaned_text[:-3]
                        cleaned_text = cleaned_text.strip()
                        
                        risk_assessment = json.loads(cleaned_text)
                        
                        # Validate required fields
                        required_fields = ["confidence", "risk_level", "recommended_action", "reasoning"]
                        if all(field in risk_assessment for field in required_fields):
                            return risk_assessment
                        else:
                            print(f"watsonx.ai response missing required fields: {risk_assessment}")
                            return fallback_response
                    
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse watsonx.ai JSON response: {e}")
                        print(f"Generated text: {generated_text}")
                        return fallback_response
                else:
                    print(f"Unexpected watsonx.ai response format: {result}")
                    return fallback_response
    
    except aiohttp.ClientError as e:
        print(f"watsonx.ai connection error: {e}")
        return fallback_response
    
    except Exception as e:
        print(f"watsonx.ai error: {e}")
        return fallback_response


async def generate_with_granite(task_type: str, context: str) -> str:
    """
    Generates text using IBM Granite model via watsonx.ai
    
    Supports two task types:
    - "commit_message": Generates conventional git commit message
    - "incident_summary": Generates 2-sentence plain English summary
    
    Args:
        task_type: Either "commit_message" or "incident_summary"
        context: Context string containing fix details
    
    Returns:
        Generated text string
    """
    
    # Fallback responses
    fallback_responses = {
        "commit_message": "fix: resolve production incident - watsonx.ai unavailable",
        "incident_summary": "Production incident detected. Fix proposed by Bob - manual review required."
    }
    
    # Validate configuration
    if not WATSONX_API_KEY or not WATSONX_PROJECT_ID:
        print(f"WARNING: watsonx.ai credentials not configured for {task_type}")
        return fallback_responses.get(task_type, "watsonx.ai unavailable")
    
    try:
        # Construct the API endpoint
        endpoint = f"{WATSONX_URL}/ml/v1/text/generation?version=2023-05-29"
        
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {WATSONX_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Prepare task-specific prompts
        if task_type == "commit_message":
            input_text = f"Generate a conventional git commit message for this fix. Return only the commit message string, nothing else. Fix: {context}"
        elif task_type == "incident_summary":
            input_text = f"Summarize this production incident fix in exactly 2 sentences for a non-technical manager. Fix: {context}"
        else:
            print(f"Unknown task_type: {task_type}")
            return fallback_responses.get(task_type, "Invalid task type")
        
        # Prepare request payload
        payload = {
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": WATSONX_PROJECT_ID,
            "input": input_text,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0
            }
        }
        
        # Make the API call
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"watsonx.ai API error {response.status}: {error_text}")
                    return fallback_responses.get(task_type, "watsonx.ai error")
                
                result = await response.json()
                
                # Extract generated text
                if "results" in result and len(result["results"]) > 0:
                    generated_text = result["results"][0].get("generated_text", "")
                    return generated_text.strip()
                else:
                    print(f"Unexpected watsonx.ai response format: {result}")
                    return fallback_responses.get(task_type, "Invalid response")
    
    except aiohttp.ClientError as e:
        print(f"watsonx.ai connection error for {task_type}: {e}")
        return fallback_responses.get(task_type, "Connection error")
    
    except Exception as e:
        print(f"watsonx.ai error for {task_type}: {e}")
        return fallback_responses.get(task_type, "Generation error")


# Made with Bob