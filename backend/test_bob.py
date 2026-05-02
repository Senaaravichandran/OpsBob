"""Test IBM Bob API connection"""
import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Get Bob API credentials
BOB_API_KEY = os.getenv("BOB_API_KEY")
BOB_API_URL = os.getenv("BOB_API_URL", "https://api.bob.ibm.com")

async def test_bob_connection():
    """Test Bob API with a simple prompt"""
    
    if not BOB_API_KEY:
        print("FAIL: BOB_API_KEY not found in .env")
        return
    
    print(f"Testing Bob API at: {BOB_API_URL}")
    print(f"Using API key: {BOB_API_KEY[:20]}...")
    print()
    
    headers = {
        "Authorization": f"Bearer {BOB_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "prompt": "Reply with just the word CONNECTED",
        "max_tokens": 50,
        "temperature": 0.3
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BOB_API_URL}/v1/generate",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                print(f"Response status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("text", result.get("content", ""))
                    print(f"Response: {response_text}")
                    
                    if response_text:
                        print("\nPASS: Bob API connection successful")
                    else:
                        print("\nFAIL: Empty response from Bob API")
                else:
                    error_text = await response.text()
                    print(f"Error response: {error_text}")
                    print("\nFAIL: Bob API returned error status")
                    
    except aiohttp.ClientError as e:
        print(f"Connection error: {e}")
        print("\nFAIL: Could not connect to Bob API")
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("\nFAIL: Test failed with exception")

if __name__ == "__main__":
    asyncio.run(test_bob_connection())

# Made with Bob
