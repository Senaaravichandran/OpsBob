import os
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Required keys
required_keys = [
    'SOURCE_FILES_PATH',
    'DEMO_SERVICE_URL',
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

issues = []

if not shutil.which('bob'):
    issues.append('bob CLI not found on PATH')

if not shutil.which('gcloud'):
    issues.append('gcloud CLI not found on PATH')
else:
    project = subprocess.run(
        ['gcloud', 'config', 'get-value', 'project'],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    region = subprocess.run(
        ['gcloud', 'config', 'get-value', 'compute/region'],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    if not project or project == '(unset)':
        issues.append('gcloud project is not configured')
    if not region or region == '(unset)':
        issues.append('gcloud compute/region is not configured')

if missing:
    print(f"Missing keys: {', '.join(missing)}")

if issues:
    print(f"Environment issues: {', '.join(issues)}")

if not missing and not issues:
    print('Environment looks ready')

# Made with Bob
