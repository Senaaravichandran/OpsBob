#!/bin/bash
# BobShell Deployment Recipe
# Deploys Bob's fix to IBM Cloud Code Engine after engineer approval
#
# Usage: ./deploy_fix.sh <incident_id> <fixed_file_path>
#
# Environment variables required:
# - ICR_NAMESPACE: IBM Container Registry namespace
# - CODE_ENGINE_APP_NAME: Code Engine application name
# - IBMCLOUD_API_KEY: IBM Cloud API key
# - IBMCLOUD_REGION: IBM Cloud region (e.g., us-south, jp-tok)

set -e  # Exit on any error

# Arguments
INCIDENT_ID=$1
FIXED_FILE_PATH=$2

# Validate arguments
if [ -z "$INCIDENT_ID" ] || [ -z "$FIXED_FILE_PATH" ]; then
    echo "ERROR: Missing required arguments"
    echo "Usage: $0 <incident_id> <fixed_file_path>"
    exit 1
fi

# Validate environment variables
if [ -z "$ICR_NAMESPACE" ] || [ -z "$CODE_ENGINE_APP_NAME" ] || [ -z "$IBMCLOUD_API_KEY" ] || [ -z "$IBMCLOUD_REGION" ]; then
    echo "ERROR: Missing required environment variables"
    echo "Required: ICR_NAMESPACE, CODE_ENGINE_APP_NAME, IBMCLOUD_API_KEY, IBMCLOUD_REGION"
    exit 1
fi

# Validate fixed file exists
if [ ! -f "$FIXED_FILE_PATH" ]; then
    echo "ERROR: Fixed file not found: $FIXED_FILE_PATH"
    exit 1
fi

echo "=========================================="
echo "BobShell Deployment Recipe"
echo "Incident ID: $INCIDENT_ID"
echo "Fixed File: $FIXED_FILE_PATH"
echo "=========================================="

# Step 1: Copy fixed file to repo
echo ""
echo "[1/7] Copying fixed file to repository..."
TARGET_FILE="demo-service/store/sessionStore.js"
cp "$FIXED_FILE_PATH" "$TARGET_FILE"
echo "✓ Fixed file copied to $TARGET_FILE"

# Step 2: Run test suite
echo ""
echo "[2/7] Running test suite..."
cd demo-service
if npm test; then
    echo "✓ All tests passed"
else
    echo "✗ TESTS FAILED — deployment aborted"
    exit 1
fi
cd ..

# Step 3: Build Docker image
echo ""
echo "[3/7] Building Docker image..."
IMAGE_TAG="us.icr.io/$ICR_NAMESPACE/payments-api:fix-$INCIDENT_ID"
cd demo-service
docker build -t "$IMAGE_TAG" .
echo "✓ Docker image built: $IMAGE_TAG"
cd ..

# Step 4: Login to IBM Container Registry and push image
echo ""
echo "[4/7] Pushing to IBM Container Registry..."
echo "$IBMCLOUD_API_KEY" | docker login -u iamapikey --password-stdin us.icr.io
docker push "$IMAGE_TAG"
echo "✓ Image pushed to registry"

# Step 5: Login to IBM Cloud
echo ""
echo "[5/7] Logging into IBM Cloud..."
ibmcloud login --apikey "$IBMCLOUD_API_KEY" -r "$IBMCLOUD_REGION" -q
ibmcloud target -r "$IBMCLOUD_REGION"
echo "✓ Logged into IBM Cloud"

# Step 6: Deploy new Code Engine revision
echo ""
echo "[6/7] Deploying to Code Engine..."
ibmcloud ce application update \
    --name "$CODE_ENGINE_APP_NAME" \
    --image "$IMAGE_TAG" \
    --quiet

REVISION_NAME="$CODE_ENGINE_APP_NAME-fix-$INCIDENT_ID"
echo "✓ Deployment initiated: $REVISION_NAME"

# Step 7: Poll until new revision is ready
echo ""
echo "[7/7] Waiting for new revision to be ready..."
TIMEOUT=120
ELAPSED=0
POLL_INTERVAL=5

while [ $ELAPSED -lt $TIMEOUT ]; do
    # Get application status
    APP_STATUS=$(ibmcloud ce application get --name "$CODE_ENGINE_APP_NAME" --output json 2>/dev/null || echo "{}")
    
    # Extract latest ready revision name
    LATEST_READY=$(echo "$APP_STATUS" | jq -r '.status.latestReadyRevisionName // empty')
    
    # Check if our revision is ready
    if echo "$LATEST_READY" | grep -q "fix-$INCIDENT_ID"; then
        echo "✓ New revision is READY: $LATEST_READY"
        echo ""
        echo "=========================================="
        echo "DEPLOYMENT SUCCESSFUL"
        echo "=========================================="
        echo "RESOLVED:$INCIDENT_ID"
        exit 0
    fi
    
    echo "  Waiting... ($ELAPSED/$TIMEOUT seconds)"
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

# Timeout reached
echo "✗ Deployment timeout after $TIMEOUT seconds"
echo "Latest ready revision: $LATEST_READY"
exit 1

# Made with Bob
