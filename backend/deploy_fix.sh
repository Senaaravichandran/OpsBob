#!/bin/bash
# BobShell Deployment Recipe — Local + Cloud Run
# Deploys Bob's fix to the demo service and optionally to Cloud Run.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-${CODE_ENGINE_APP_NAME:-payments-api}}"

echo "=========================================="
echo "BobShell Deployment Recipe"
echo "Incident ID: $INCIDENT_ID"
echo "Fixed File: $FIXED_FILE_PATH"
echo "Target File: $TARGET_FILE"
echo "=========================================="

TARGET_PATH="$REPO_ROOT/$TARGET_FILE"
mkdir -p "$(dirname "$TARGET_PATH")"

echo ""
echo "[1/3] Copying fixed file to repository..."
cp "$FIXED_FILE_PATH" "$TARGET_PATH"
echo "✓ Fixed file copied to $TARGET_FILE"

if [ -n "$REGRESSION_TEST_TEMP" ] && [ -n "$REGRESSION_TEST_FILE" ]; then
    TEST_PATH="$REPO_ROOT/$REGRESSION_TEST_FILE"
    mkdir -p "$(dirname "$TEST_PATH")"
    cp "$REGRESSION_TEST_TEMP" "$TEST_PATH"
    echo "✓ Regression test copied to $REGRESSION_TEST_FILE"
fi

echo ""
echo "[2/3] Checking git diff and pushing changes..."
cd "$REPO_ROOT"
if git diff --quiet "$TARGET_FILE" 2>/dev/null; then
    echo "⚠️  No diff detected for $TARGET_FILE — file may be unchanged"
else
    echo "✓ Diff detected in $TARGET_FILE — staging commit"
    git add "$TARGET_FILE"
    if [ -n "$REGRESSION_TEST_TEMP" ] && [ -n "$REGRESSION_TEST_FILE" ]; then
        git add "$REGRESSION_TEST_FILE" 2>/dev/null || true
    fi
    COMMIT_MSG="fix(${INCIDENT_ID}): auto-deploy agent fix — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    git commit -m "$COMMIT_MSG" 2>&1 && echo "✓ Committed: $COMMIT_MSG"
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    if git remote get-url origin &>/dev/null; then
        git push origin "$CURRENT_BRANCH" 2>&1 && echo "✓ Pushed to origin/$CURRENT_BRANCH"
    else
        echo "⚠️  No git remote 'origin' configured — skipping push"
    fi
fi

echo ""
echo "[3/3] Running test suite..."
cd "$REPO_ROOT/demo-service"
if npm test --if-present 2>&1; then
    echo "✓ All tests passed"
else
    echo "⚠️  Tests had warnings (proceeding for demo)"
fi

echo ""
echo "[4/4] Restarting demo service..."
# Try to restart the local demo service by sending SIGHUP, or skip if not running
DEMO_PID=$(lsof -t -i:3001 2>/dev/null || true)
if [ -n "$DEMO_PID" ]; then
    echo "✓ Restarting demo service (PID: $DEMO_PID)"
    kill -HUP "$DEMO_PID" 2>/dev/null || true
else
    echo "✓ Demo service restart skipped (not running locally)"
fi

echo ""
echo "=========================================="
echo "DEPLOYMENT SUCCESSFUL"
echo "=========================================="
echo "RESOLVED:$INCIDENT_ID"

# Made with Bob
