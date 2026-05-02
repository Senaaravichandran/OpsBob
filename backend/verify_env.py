"""Verify .env file has all required keys"""
from dotenv import load_dotenv
import os
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Required keys
required_keys = [
    'BOB_API_KEY',
    'IBM_CLOUD_API_KEY',
    'IBM_CLOUD_REGION',
    'CODE_ENGINE_PROJECT',
    'WATSONX_API_KEY',
    'WATSONX_PROJECT_ID',
    'WATSONX_URL'
]

# Check which keys exist
missing = []
for key in required_keys:
    value = os.getenv(key)
    if not value:
        missing.append(key)

# Print result
if not missing:
    print("All keys found")
else:
    print(f"Missing keys: {', '.join(missing)}")

# Made with Bob
