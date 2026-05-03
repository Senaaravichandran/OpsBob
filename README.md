# OpsBob

OpsBob is an IBM-focused production intelligence demo for autonomous SRE response. It ingests an incident, enriches it with Instana-style metrics and traces, asks IBM Bob to diagnose and generate a fix, uses IBM watsonx.ai Granite for risk and report generation, routes verification through IBM watsonx Orchestrate, and streams the whole workflow to an IBM Carbon React dashboard.

The demo incident is a real Node.js memory leak in `demo-service`: an unbounded in-memory `Map` grows under payment traffic. OpsBob reads that source code, identifies the leak, generates a structured replacement file plus optional regression test, verifies the result, and deploys the approved fix through BobShell.

## IBM Focus

| IBM capability | How this repo uses it |
| --- | --- |
| IBM Bob shell | Runs the three analysis phases: `ask`, `plan`, and `code`. The backend calls Bob non-interactively through `backend/bob_client.py`. |
| IBM watsonx.ai | Uses Granite through `backend/watsonx_client.py` for structured risk assessment, incident summaries, and post-incident report text. |
| IBM Granite | Default model is `ibm/granite-4-h-small`, configurable with `WATSONX_MODEL_ID`. |
| IBM watsonx Orchestrate | Invokes a commander agent through `backend/orchestrate_client.py` and exposes tool endpoints for static analysis, tests, approval routing, and post-incident reporting. |
| IBM Instana | `mcp-server/` provides MCP tools for active incidents, service metrics, and stack traces. With Instana credentials it calls Instana APIs; without them it falls back to live demo-service data. |
| IBM Carbon Design System | The frontend uses `@carbon/react`, Carbon icons, IBM Plex styling, and a dark operations dashboard. |
| IBM Cloud target | The environment template includes IBM Cloud / Code Engine variables. The current checked-in deploy script applies fixes locally and restarts the demo service; Code Engine deployment is an architecture target, not the active script behavior. |

## Current Runtime Flow

```text
Instana or demo webhook
  -> FastAPI backend /webhook
  -> MCP enrichment from Instana or local demo-service fallback
  -> source-code context assembled from demo-service files
  -> IBM Bob shell ask/plan/code stream
  -> watsonx.ai Granite risk assessment
  -> local 3-agent verification pipeline
  -> watsonx Orchestrate commander decision
  -> BobShell deploy stream when approved
  -> post-incident report and incident-history.json update
  -> React + Carbon dashboard over SSE
```

## Project Structure

```text
backend/                 FastAPI orchestration layer
  main.py                Webhooks, SSE streams, approval, deploy, Orchestrate tool APIs
  bob_client.py          IBM Bob shell integration and structured fix parsing
  watsonx_client.py      watsonx.ai / Granite client
  orchestrate_client.py  watsonx Orchestrate commander invocation
  orchestrate_agents.py  Static analysis, test runner, approval router, report agent
  mcp_client.py          Python client for the Instana MCP server
  bobshell.py            Applies Bob's fix and streams deployment audit logs
  deploy_fix.sh          Local deployment recipe for the demo service

demo-service/            Payments API with intentional memory leaks
  server.js              Main Express service and leaking /payment route
  metrics.js             Real process memory metrics
  debug/traces.js        Local stack-trace capture fallback
  store/sessionStore.js  Secondary leaking in-memory session store
  test/                  Mocha tests

mcp-server/              TypeScript MCP server for Instana-style observability tools
frontend/                React + Vite + IBM Carbon dashboard
orchestrate/             watsonx Orchestrate agent YAML definitions
orchestrate_skill.json   Skill definition for review_bob_fix
incident-history.json    Institutional memory from resolved incidents
landing/                 Standalone Carbon-themed landing page
tasks/, docs/            Analysis notes, verification plans, and historical docs
```

Generated or runtime-heavy directories such as `node_modules`, `venv`, `.venv`, `__pycache__`, logs, and `demo-service1` through `demo-service4` are not part of the core source flow.

## Prerequisites

- Node.js 18+
- Python 3.9+; Python 3.12 is used by the backend Dockerfile
- npm
- Bash-compatible shell for `*.sh` scripts, such as Git Bash or WSL on Windows
- IBM Bob shell available as `bob`, or the vendored backend runtime at `backend/vendor/bob.js`
- IBM Cloud API key with watsonx.ai access
- Optional: IBM Instana tenant and API token
- Optional: watsonx Orchestrate instance, agent, and environment IDs

## Environment

Copy the template and fill the IBM values:

```bash
cp .env.example .env
```

Key variables:

```env
# IBM Bob
BOB_API_KEY=your_bob_api_key_here
BOB_API_URL=https://api.bob.ibm.com

# IBM watsonx.ai / Granite
WATSONX_API_KEY=your_watsonx_api_key_here
WATSONX_PROJECT_ID=your_project_id_here
WATSONX_SPACE_ID=
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-4-h-small

# IBM watsonx Orchestrate
ORCHESTRATE_HOST=https://api.us-south.watson-orchestrate.cloud.ibm.com
ORCHESTRATE_INSTANCE_ID=your_instance_id
ORCHESTRATE_AGENT_ID=your_commander_agent_id
ORCHESTRATE_ENV_ID=your_environment_id
BACKEND_URL=http://localhost:8000

# IBM Instana, optional
INSTANA_BASE_URL=https://your-tenant.instana.io
INSTANA_API_TOKEN=your_instana_api_token_here

# Local demo
SOURCE_FILES_PATH=demo-service
DEMO_SERVICE_URL=http://localhost:3001
BACKEND_PORT=8000
DASHBOARD_URL=http://localhost:3000
```

The backend exchanges IBM Cloud API keys for IAM bearer tokens in `backend/iam_auth.py`; watsonx.ai and Orchestrate calls should not use the raw API key directly as a bearer token.

## Install

```bash
cd backend
pip install -r requirements.txt
cd ..

cd demo-service
npm install
cd ..

cd mcp-server
npm install
npm run build
cd ..

cd frontend
npm install
cd ..
```

## Run Locally

Terminal 1, demo payments API:

```bash
cd demo-service
npm start
```

Terminal 2, backend:

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 3, frontend:

```bash
cd frontend
VITE_BACKEND_TARGET=http://localhost:8000 npm run dev
```

On PowerShell:

```powershell
cd frontend
$env:VITE_BACKEND_TARGET="http://localhost:8000"
npm run dev
```

Open `http://localhost:3000`.

## Trigger A Demo Incident

With the backend and demo service running:

```bash
bash demo-trigger.sh
```

Or trigger manually:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"service":"payments-api","severity":"HIGH","type":"MEMORY_LEAK","incidentId":"INC-DEMO-001","message":"Memory usage growing; threshold exceeded"}'
```

In the dashboard, select the incident and click `ANALYZE WITH BOB`. The center panel streams Bob's `ask`, `plan`, and `code` phases, the Granite risk card, the verification pipeline, and the watsonx Orchestrate commander decision. If approved, deployment logs stream through BobShell.

## API Surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/webhook` | Receives Instana or mock incidents and assembles Bob context. |
| `GET` | `/stream/{incidentId}` | Streams Bob analysis, Granite risk, verification, and Orchestrate commander events. |
| `POST` | `/approve/{incidentId}` | Manual approval fallback after verification completes. |
| `GET` | `/deploy-stream/{incidentId}` | Streams BobShell fix application and post-incident reporting. |
| `GET` | `/orchestrate/stream/{incidentId}` | Direct watsonx Orchestrate commander run as SSE. |
| `POST` | `/orchestrate/decision` | Receives approve, escalate, or reject decisions. |
| `POST` | `/orchestrate/static-analysis` | Tool endpoint for StaticAnalysisAgent. |
| `POST` | `/orchestrate/run-tests` | Tool endpoint for TestRunnerAgent. |
| `POST` | `/orchestrate/route-approval` | Tool endpoint for ApprovalRouterAgent. |
| `POST` | `/orchestrate/post-incident` | Tool endpoint for PostIncidentReportAgent. |
| `GET` | `/system-health` | Checks Bob shell, watsonx.ai, Orchestrate, Instana, and demo-service health. |
| `GET` | `/runbook` | Returns `incident-history.json`. |
| `GET` | `/audit/{incidentId}` | Returns incident details, pipeline results, and report data. |

## Orchestrate Registration

The repo includes two Orchestrate registration surfaces:

- `orchestrate_skill.json` defines `review_bob_fix`, whose endpoint is `POST {BACKEND_URL}/orchestrate/decision`.
- `orchestrate/*.yaml` defines the specialist agents for static analysis, test running, approval routing, and post-incident reporting.

For real Orchestrate tool calls, your backend must be reachable by Orchestrate. Update `BACKEND_URL` and the tool server bindings to a public HTTPS URL, then publish the tools and commander agent in your watsonx Orchestrate environment.

Helper scripts in `backend/_patch_tools.py`, `_patch_schemas.py`, and `_patch_agents.py` were used for patching existing Orchestrate tool definitions. Treat them as admin utilities and review IDs before running them against another instance.

## Tests And Checks

```bash
cd demo-service
npm test

cd ../mcp-server
npm run build

cd ../frontend
npm run build
```

Backend smoke checks:

```bash
cd backend
python -m py_compile main.py bob_client.py watsonx_client.py orchestrate_client.py orchestrate_agents.py
python verify_env.py
```

`verify_env.py` still checks for `gcloud` because earlier deployment work targeted Cloud Run. That check is legacy relative to the IBM-centered architecture and the current local `deploy_fix.sh` behavior.

## Demo Reality Notes

- Instana is optional for local demos. If Instana is not configured, MCP tools call `demo-service` endpoints for real heap metrics and local traces.
- watsonx.ai calls have safe fallbacks when credentials, project association, or model runtime are unavailable.
- watsonx Orchestrate commander calls fall back to the local verification pipeline if Orchestrate is unavailable.
- Bob analysis requires a working Bob shell runtime and API credentials; otherwise `/stream/{incidentId}` emits an analysis error.
- The active deploy recipe writes Bob's structured fixed file into the workspace, optionally writes a generated regression test, runs the demo-service test suite, and restarts the local Node process when it is running on port `3001`.

## License

MIT
