#!/bin/bash
# BobShell Deployment Recipe
# Deploys Bob's fix to Google Cloud Run after engineer approval.
#
# Usage: ./deploy_fix.sh <incident_id> <fixed_file_path> <target_file> [regression_test_temp] [regression_test_file]

set -euo pipefail

INCIDENT_ID=${1:-}
FIXED_FILE_PATH=${2:-}
TARGET_FILE=${3:-}
REGRESSION_TEST_TEMP=${4:-}
REGRESSION_TEST_FILE=${5:-}

if [ -z "$INCIDENT_ID" ] || [ -z "$FIXED_FILE_PATH" ] || [ -z "$TARGET_FILE" ]; then
    echo "ERROR: Missing required arguments"
    echo "Usage: $0 <incident_id> <fixed_file_path> <target_file> [regression_test_temp] [regression_test_file]"
    exit 1
fi

if [ ! -f "$FIXED_FILE_PATH" ]; then
    echo "ERROR: Fixed file not found: $FIXED_FILE_PATH"
    exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
    echo "ERROR: gcloud CLI is not installed or not on PATH"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-${CODE_ENGINE_APP_NAME:-payments-api}}"
GCLOUD_PROJECT="${GCLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
GCLOUD_REGION="${GCLOUD_REGION:-$(gcloud config get-value compute/region 2>/dev/null || true)}"

if [ -z "$GCLOUD_REGION" ]; then
    GCLOUD_REGION="$(gcloud config get-value run/region 2>/dev/null || true)"
fi

if [ -z "$GCLOUD_PROJECT" ] || [ -z "$GCLOUD_REGION" ]; then
    echo "ERROR: gcloud project or region is not configured"
    echo "Project: ${GCLOUD_PROJECT:-<empty>}"
    echo "Region: ${GCLOUD_REGION:-<empty>}"
    exit 1
fi

echo "=========================================="
echo "BobShell Deployment Recipe"
echo "Incident ID: $INCIDENT_ID"
echo "Fixed File: $FIXED_FILE_PATH"
echo "Target File: $TARGET_FILE"
echo "Cloud Run Service: $SERVICE_NAME"
echo "Project: $GCLOUD_PROJECT"
echo "Region: $GCLOUD_REGION"
echo "=========================================="

TARGET_PATH="$REPO_ROOT/$TARGET_FILE"
mkdir -p "$(dirname "$TARGET_PATH")"

echo ""
echo "[1/4] Copying fixed file to repository..."
cp "$FIXED_FILE_PATH" "$TARGET_PATH"
echo "✓ Fixed file copied to $TARGET_FILE"

if [ -n "$REGRESSION_TEST_TEMP" ] && [ -n "$REGRESSION_TEST_FILE" ]; then
    TEST_PATH="$REPO_ROOT/$REGRESSION_TEST_FILE"
    mkdir -p "$(dirname "$TEST_PATH")"
    cp "$REGRESSION_TEST_TEMP" "$TEST_PATH"
    echo "✓ Regression test copied to $REGRESSION_TEST_FILE"
fi

echo ""
echo "[2/4] Running test suite..."
cd "$REPO_ROOT/demo-service"
if npm test; then
    echo "✓ All tests passed"
else
    echo "✗ TESTS FAILED — deployment aborted"
    exit 1
fi

echo ""
echo "[3/4] Deploying demo service to Cloud Run..."
cd "$REPO_ROOT"
gcloud run deploy "$SERVICE_NAME" \
    --source "$REPO_ROOT/demo-service" \
    --project "$GCLOUD_PROJECT" \
    --region "$GCLOUD_REGION" \
    --allow-unauthenticated \
    --quiet
echo "✓ Cloud Run deployment completed"

echo ""
echo "[4/4] Verifying deployed service..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --platform managed \
    --project "$GCLOUD_PROJECT" \
    --region "$GCLOUD_REGION" \
    --format='value(status.url)')

if [ -z "$SERVICE_URL" ]; then
    echo "ERROR: Unable to determine deployed service URL"
    exit 1
fi

curl -fsS "$SERVICE_URL/health" >/dev/null
echo "✓ Deployment health check passed: $SERVICE_URL/health"

echo ""
echo "=========================================="
echo "DEPLOYMENT SUCCESSFUL"
echo "=========================================="
echo "RESOLVED:$INCIDENT_ID"

# Made with Bob
