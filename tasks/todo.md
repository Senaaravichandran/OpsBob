# OpsBob Verification Plan

- [x] Read the documented architecture and key runtime paths
- [x] Verify local prerequisites, environment, and dependency state
- [x] Run focused unit/build checks for backend, frontend, demo-service, and MCP server
- [x] Start the runnable stack needed for validation
- [x] Exercise backend HTTP endpoints directly
- [x] Exercise the frontend in a browser and validate major UI flows
- [x] Record pass/fail results, blockers, and evidence

## Review

- Fixed a backend syntax error in `backend/bob_client.py` that prevented the FastAPI app from importing.
- Added the missing `demo-service/debug/traces.js` module so the demo service can start and expose `/debug/traces`.
- Fixed failed-analysis handling so Bob connectivity failures now persist as `analysis_failed`, block `/approve`, and surface correctly in the dashboard without showing the deploy action.
- Verified: demo-service tests pass; frontend production build passes; MCP TypeScript build passes; backend compiles and imports; local stack runs on ports 3001, 8000, and 3000.
- Verified: backend `/health`, `/system-health`, `/webhook`, `/stream`, `/audit`, `/runbook`, `/memory-stats`, `/incident-queue`, `/orchestrate/prepare/{incidentId}`, `/approve/{incidentId}`, `/orchestrate/decision`, and deploy-stream approval gating; demo-service `/health`, `/metrics`, `/payment`; browser landing, dashboard load, and live analyze flow initiation.
- Migrated Bob integration from direct HTTP API calls to Bob shell CLI with stdin prompt delivery, structured code-payload parsing, retry-on-schema-drift, and Windows-safe executable resolution.
- Fixed Python MCP integration with the proper initialize → initialized → tools/list → tools/call handshake, rebuilt the MCP server, and verified live webhook enrichment now reaches the MCP server without backend fallback.
- Switched deployment orchestration from IBM Cloud Code Engine to gcloud Cloud Run, updated health/startup/env checks for Bob shell and gcloud, and fixed the local pipeline test runner to execute `npm test` on Windows without fallback.
- Fixed watsonx auth in the backend by exchanging IBM Cloud API keys for IAM access tokens, added configurable `WATSONX_MODEL_ID` and `WATSONX_SPACE_ID` support, and moved the default model to `ibm/granite-4-h-small`.
- Added real FastAPI tool endpoints for `/orchestrate/static-analysis`, `/orchestrate/run-tests`, `/orchestrate/route-approval`, and `/orchestrate/post-incident`, then verified they appear in `/openapi.json` and execute successfully with focused requests.
- Blockers remaining: watsonx.ai and watsonx Orchestrate generation/auth flows still return 401 with the current credentials, so static-analysis/report quality remains on fallback behavior; the Cloud Run happy-path deploy was not executed because the generated Bob fix is not trustworthy enough to apply unreviewed to the workspace during verification.
- Blockers remaining: watsonx auth now works, but watsonx generation still returns `403 no_associated_service_instance_error` because the current project is not associated to a usable WML runtime through the supported IBM flow; the Cloud Run happy-path deploy was not executed because the generated Bob fix is not trustworthy enough to apply unreviewed to the workspace during verification.

## Migration Plan

- [x] Replace Bob HTTP calls with non-interactive Bob shell CLI calls
- [x] Store structured code-generation output needed for deployment
- [x] Implement a correct MCP stdio initialize + tools/call handshake in Python
- [x] Normalize MCP tool responses to the shapes the backend expects
- [x] Switch deployment from IBM Cloud Code Engine to gcloud Cloud Run
- [x] Update stale health/startup/config surfaces that still assume Bob API or IBM Cloud deployment
- [x] Validate the migrated flow with focused compile/build/runtime checks

## Production Bob CLI Fix

- [ ] Vendor the proven local Bob bundle into the backend build context
- [ ] Resolve Bob execution through the local bundle when PATH does not provide `bob`
- [ ] Update runtime health checks and container image requirements for the bundled Bob path
- [ ] Validate the bundled fallback locally without relying on the globally installed Bob wrapper
- [ ] Redeploy the backend and re-run the frontend browser flow against production

## Local Live Orchestration UI

- [ ] Wire pipeline progress callbacks into the existing `/stream/{incidentId}` SSE flow
- [ ] Add a center-panel live orchestration card for `Brainstorm`, `Plan`, and `Execute`
- [ ] Preserve existing dashboard actions while showing live agent outputs inline
- [ ] Run the backend, demo service, and frontend locally and verify the full UI flow
- [ ] Capture any blockers found during local verification