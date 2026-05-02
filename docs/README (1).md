# OpsBob — Autonomous Production Self-Healing Platform

> *"Bob protects your production revenue while your team sleeps."*

OpsBob is a real-time production incident response platform powered by IBM Bob Orchestrator. When a production anomaly is detected, OpsBob automatically diagnoses the root cause, proposes a code fix, runs a four-agent watsonx Orchestrate verification pipeline, and applies the fix — all within a governed, human-approved loop.

**Mean Time To Resolution: from 3–4 hours to under 5 minutes.**

---

## Hackathon Account Constraints — Honest Notes

| Component | Demo Reality | Production Target |
|---|---|---|
| **Demo microservice** | Runs locally on demo machine | IBM Cloud Code Engine |
| **BobShell deployment** | Applies fix locally, restarts Node process | `ibmcloud ce application update` |
| **Instana** | Trial account — alert webhook + basic metrics | Full Instana with deep APM |
| **Stack traces** | From demo service's own `/debug/traces` endpoint | Instana `/api/v1/events/{id}` |
| **Memory metrics** | Demo service `/metrics` endpoint (real heap data) | Instana infrastructure monitoring |

Everything else — Bob API, watsonx.ai, watsonx Orchestrate, Granite, Carbon UI — runs live and real with no scaffolding.

---

## IBM Technology Stack

| Technology | Role | Status |
|---|---|---|
| **IBM Bob Orchestrator** | Core engine — reads code, diagnoses root cause, writes fix and regression tests | Live |
| **IBM Instana (Trial)** | Alert trigger — fires real webhook when memory threshold crossed | Live (trial) |
| **IBM watsonx.ai** | Risk intelligence — evaluates Bob's fix, returns structured risk score | Live |
| **IBM Granite (granite-3-8b-instruct)** | Lightweight tasks — commit messages, incident summaries via watsonx.ai | Live |
| **IBM watsonx Orchestrate** | Four-agent verification pipeline — static analysis, test runner, approval router, post-incident report | Live |
| **IBM Carbon Design System** | Enterprise dashboard UI | Live |
| **IBM Cloud Code Engine** | Production deployment runtime (architecture target) | Architecture |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          OPSBOB SYSTEM                               │
│                                                                      │
│  ┌─────────────┐  webhook   ┌──────────────────────────────────┐    │
│  │   INSTANA   │───────────▶│        FASTAPI BACKEND           │    │
│  │  (Trial)    │            │                                  │    │
│  │  Alert on   │            │  1. Parse Instana alert payload  │    │
│  │  mem > 250MB│            │  2. Fetch stack traces (/debug)  │    │
│  └─────────────┘            │  3. Fetch metrics (/metrics)     │    │
│                             │  4. Load source files from disk  │    │
│  ┌─────────────┐            │  5. Assemble Bob context         │    │
│  │ DEMO SERVICE│◀── poll ──│  6. Call Bob Orchestrator        │    │
│  │ (local Node)│            │  7. Stream response via SSE      │    │
│  │             │            │  8. Call watsonx.ai risk assess  │    │
│  │ /metrics    │            │  9. Trigger Orchestrate pipeline │    │
│  │ /debug/trace│            └──────────────┬───────────────────┘    │
│  └─────────────┘                           │ SSE stream             │
│                                            ▼                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │           WATSONX ORCHESTRATE — 4 AGENT PIPELINE            │   │
│  │                                                              │   │
│  │  [1] StaticAnalysisAgent                                     │   │
│  │      Sends Bob's diff to watsonx.ai for security review      │   │
│  │      Checks: null risks, side effects, logic errors          │   │
│  │      Output: PASS / WARN / FAIL + findings list              │   │
│  │                         ↓                                    │   │
│  │  [2] TestRunnerAgent                                         │   │
│  │      Executes: npm test on the fixed code                    │   │
│  │      (Bob wrote the regression tests — this agent runs them) │   │
│  │      Output: pass count, fail count, coverage %             │   │
│  │                         ↓                                    │   │
│  │  [3] ApprovalRouterAgent                                     │   │
│  │      Routes based on: risk score + static verdict + tests    │   │
│  │      high+pass+low  → recommend auto-approve                 │   │
│  │      medium/warn    → route to on-call engineer              │   │
│  │      fail/high risk → escalate to senior, block deploy       │   │
│  │                         ↓  (after human approves)            │   │
│  │  [4] PostIncidentReportAgent                                 │   │
│  │      Generates: timeline, root cause, fix summary, runbook   │   │
│  │      Writes to: incident-history.json (institutional memory) │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │ decision                                   │
│                         ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              REACT DASHBOARD (IBM Carbon Design)             │   │
│  │                                                              │   │
│  │  [Incident Feed] │ [Bob Diagnosis + Risk Card] │ [Actions]  │   │
│  │                  │ [Agent Pipeline Status]     │            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                         │ Approve clicked                           │
│                         ▼                                           │
│  ┌──────────────────┐                                               │
│  │    BOBSHELL      │  run tests → write fix → restart service     │
│  │  (local demo)    │  → poll /metrics → confirm stable →          │
│  │  Code Engine     │  emit RESOLVED → PostIncidentAgent runs      │
│  │  (production)    │                                               │
│  └──────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## The Four watsonx Orchestrate Agents

### Agent 1 — StaticAnalysisAgent
**Job:** Validate Bob's code fix before it touches any environment.

Sends Bob's code diff to watsonx.ai (Granite) with a security and correctness prompt. Checks for new null pointer risks, security issues, logic errors, and whether the fix actually targets the identified root cause. Returns `PASS`, `WARN`, or `FAIL` with specific findings.

If `FAIL` — the Approve button is replaced with "Escalate Only" and deployment is blocked entirely.

### Agent 2 — TestRunnerAgent
**Job:** Run the regression tests that Bob wrote.

Calls the backend's `/run-tests` endpoint which executes `npm test` against the patched source file. Bob wrote the test that specifically covers the fixed code path — this agent proves it passes. Reports pass/fail/skipped counts and whether the memory-leak-specific test now passes.

### Agent 3 — ApprovalRouterAgent
**Job:** Decide who approves this fix and surface that recommendation to the engineer.

```
confidence=high + static=PASS + tests=pass + risk=low
  → Recommended: Approve (engineer still clicks)

confidence=medium OR static=WARN OR risk=medium
  → Recommended: Review carefully before approving

tests=failing OR static=FAIL OR risk=high
  → Recommended: Escalate — do not deploy
```

The routing decision and its reasoning appear on the dashboard **before** the action buttons. The engineer sees why they are being asked, not just that they should act.

### Agent 4 — PostIncidentReportAgent
**Job:** Generate an incident report and update the runbook after resolution.

Runs automatically when BobShell emits `RESOLVED`. Uses Granite via watsonx.ai to write a timestamped incident timeline, plain-English root cause summary, fix description, and preventive recommendations. Appends everything to `incident-history.json`.

On the **next incident** of the same type, Bob's context prompt includes the previous resolution. OpsBob builds institutional memory with every fix.

---

## Demo Flow — The 2:14 AM Scenario

| Time | Event | What's Real |
|---|---|---|
| T+0 | Load generator starts (50 RPS) | Real traffic |
| T+2min | Heap grows from ~50MB to ~280MB | Real Node.js memory leak |
| T+3min | Instana trial alert fires webhook | Real Instana webhook |
| T+3:05 | Backend fetches stack trace + heap data from local service | Real data |
| T+3:10 | Bob starts streaming: Ask → Plan → Code | Real Bob API |
| T+4:00 | watsonx.ai Risk Card appears on dashboard | Real watsonx.ai |
| T+4:05 | Orchestrate: StaticAnalysisAgent runs | Real agent |
| T+4:10 | Orchestrate: TestRunnerAgent runs | Real npm test |
| T+4:15 | Orchestrate: ApprovalRouterAgent routes to engineer | Real routing |
| T+4:25 | Engineer reads all outputs, clicks Approve | One button |
| T+4:30 | BobShell writes fix, restarts service | Real execution |
| T+4:50 | /metrics shows heap dropping to ~55MB | Real recovery |
| T+5:00 | PostIncidentReportAgent generates report | Real Granite output |
| T+5:10 | Incident closes: "Resolved by Bob" | Dashboard |

---

## Project Structure

```
opsbob/
├── backend/
│   ├── main.py                       # FastAPI — webhook, SSE, approve, agent callbacks
│   ├── bob_client.py                 # IBM Bob Orchestrator API
│   ├── bobshell.py                   # Local fix execution + audit trail
│   ├── mcp_client.py                 # Instana MCP (trial-compatible)
│   ├── watsonx_client.py             # watsonx.ai + Granite inference
│   ├── orchestrate_agents.py         # Four agent trigger + callback functions
│   ├── deploy_fix.sh                 # BobShell recipe (local + Code Engine)
│   ├── verify_env.py                 # Startup env validation
│   └── requirements.txt
│
├── frontend/src/components/
│   ├── IncidentFeed.jsx              # Left panel — live alerts
│   ├── DiagnosisCard.jsx             # Centre — Bob streaming output
│   ├── RiskAssessmentCard.jsx        # Centre — watsonx.ai risk score
│   ├── CodeDiff.jsx                  # Centre — syntax-highlighted diff
│   ├── AgentPipelineStatus.jsx       # Centre — 4-agent live status
│   └── FixActions.jsx                # Right — approve/escalate + timeline
│
├── mcp-server/
│   └── index.js                      # Instana MCP (trial-safe endpoints only)
│
├── demo-service/
│   ├── src/
│   │   ├── routes/payments.js        # Leaking endpoint
│   │   ├── middleware/session.js
│   │   ├── store/sessionStore.js     # Bug: Map never cleared
│   │   └── debug/traces.js           # Exposes stack traces locally
│   ├── metrics.js                    # Exposes /metrics — real heap data
│   ├── load-generator.js
│   └── Dockerfile
│
├── orchestrate/
│   ├── static_analysis_agent.json
│   ├── test_runner_agent.json
│   ├── approval_router_agent.json
│   └── post_incident_agent.json
│
├── incident-history.json             # Runbook — grows with every resolved incident
├── startup.sh
├── stop-demo.sh
├── .env.example
└── README.md
```

---

## Environment Variables

```bash
# IBM Bob
BOB_API_KEY=
BOB_API_ENDPOINT=

# IBM Instana (trial — only webhook needed)
INSTANA_BASE_URL=           # https://your-tenant.instana.io
INSTANA_API_TOKEN=

# IBM watsonx.ai
WATSONX_API_KEY=
WATSONX_PROJECT_ID=
WATSONX_URL=                # https://us-south.ml.cloud.ibm.com

# IBM watsonx Orchestrate
ORCHESTRATE_BASE_URL=
ORCHESTRATE_API_TOKEN=

# Demo service (local)
DEMO_SERVICE_URL=           # http://localhost:3001
SOURCE_FILES_PATH=          # absolute path to demo-service/src

# Dashboard
DASHBOARD_URL=              # http://localhost:3000
BACKEND_PORT=8000
MCP_SERVER_PORT=3001

# IBM Cloud — not required for local demo, needed for Code Engine production path
IBMCLOUD_API_KEY=
IBMCLOUD_REGION=
ICR_NAMESPACE=
CODE_ENGINE_APP_NAME=       # payments-api
```

---

## Setup

### Step 1 — Install Dependencies

```bash
cd backend && pip install -r requirements.txt
cd mcp-server && npm install
cd frontend && npm install
cd demo-service && npm install
```

### Step 2 — Validate Environment

```bash
bash startup.sh
```

Validates all vars, starts MCP server + FastAPI backend + demo service + frontend. Prints each service URL when ready.

### Step 3 — Register Orchestrate Agents

In your watsonx Orchestrate instance:
1. **Skills → Add Skill** — upload each JSON from `orchestrate/` folder
2. Set each skill's endpoint to your backend:
   - `static_analysis_agent.json` → `POST http://<backend>/orchestrate/static-analysis`
   - `test_runner_agent.json` → `POST http://<backend>/orchestrate/run-tests`
   - `approval_router_agent.json` → `POST http://<backend>/orchestrate/route-approval`
   - `post_incident_agent.json` → `POST http://<backend>/orchestrate/post-incident`
3. Create an **Agent** that runs all four in sequence

### Step 4 — Configure Instana Alert

1. Instana → **Events → Custom Events → New**
2. Metric: `nodejs.heap_used` growth > 20MB/min, window: 1 minute
3. Alert channel: Webhook → `http://<your-backend>/webhook`
4. Click **Test Alert** — confirm backend logs "Webhook received"

Fallback if trial blocks custom metric: use **Sudden Increase** built-in alert type on `payments-api`.

### Step 5 — Run the Demo

```bash
# Terminal 1
bash startup.sh

# Terminal 2 — trigger the leak
node demo-service/load-generator.js --rps 50

# Terminal 3 — watch memory
watch -n 3 'curl -s http://localhost:3001/metrics | jq ".heap_used_mb"'

# Browser
open http://localhost:3000
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook` | Receives Instana alert, assembles context, calls Bob |
| `GET` | `/stream/{incident_id}` | SSE — Bob output + agent pipeline events |
| `POST` | `/approve` | Triggers BobShell fix execution |
| `POST` | `/orchestrate/static-analysis` | StaticAnalysisAgent callback |
| `POST` | `/orchestrate/run-tests` | TestRunnerAgent callback |
| `POST` | `/orchestrate/route-approval` | ApprovalRouterAgent callback |
| `POST` | `/orchestrate/post-incident` | PostIncidentReportAgent callback |
| `POST` | `/orchestrate/decision` | Final human decision (approve/escalate/reject) |
| `GET` | `/incidents` | All active and resolved incidents |
| `GET` | `/audit/{incident_id}` | Full BobShell audit trail |
| `GET` | `/runbook` | Contents of incident-history.json |

---

## Bob Prompts Used to Build This System

```
[Ask] Scaffold a Python FastAPI application with a POST /webhook 
endpoint and a GET /stream SSE endpoint for real-time streaming.
```

```
[Code] Build a Node.js MCP server wrapping Instana REST API.
Expose three tools: get_active_incidents, get_service_metrics,
get_stack_traces. Read INSTANA_BASE_URL and INSTANA_API_TOKEN 
from env. On non-200, return structured error not throw.
```

```
[Code] Rewrite the FastAPI /webhook endpoint to assemble Bob's 
context dynamically at runtime from: real Instana alert payload, 
stack traces from /debug/traces, heap data from /metrics, and 
source files loaded from disk. Call Bob Orchestrator API and 
stream response via SSE with phase labels: ask, plan, code, done.
```

```
[Code] Create backend/watsonx_client.py with:
call_watsonx_risk_assessment(bob_plan_text) — calls 
ibm/granite-3-8b-instruct, returns structured risk JSON.
generate_with_granite(task_type, context) — handles 
commit_message and incident_summary task types.
On any error return a safe fallback object, never raise.
```

```
[Code] Create backend/orchestrate_agents.py with four async 
functions that trigger and handle callbacks for:
StaticAnalysisAgent, TestRunnerAgent, ApprovalRouterAgent,
PostIncidentReportAgent. Each POSTs to Orchestrate API and 
handles the async callback via the /orchestrate/* endpoints.
Also generate the four skill definition JSON files.
```

```
[Code] Write deploy_fix.sh for local BobShell execution:
copy fixed file to correct path, run npm test, if pass restart 
the Node.js service with the patched code, poll /metrics every 
3 seconds until heap_used drops below 100MB, then print 
RESOLVED:{incident_id}. Exit 1 if tests fail.
```

```
[Code] Add RiskAssessmentCard.jsx and AgentPipelineStatus.jsx 
to the React dashboard using IBM Carbon Design System only.
RiskAssessmentCard: confidence, risk level, blast radius, 
recommended action tags. AgentPipelineStatus: four steps with 
live running/pass/fail/blocked status indicators using Carbon 
ProgressIndicator. Both receive data from the SSE stream.
```

---

## Edge Cases Handled

| Edge Case | Handling |
|---|---|
| Instana trial blocks deep stack trace API | Demo service exposes `/debug/traces` with real Node.js Error stack |
| Instana trial blocks custom metric alerts | Fall back to Sudden Increase built-in alert type |
| Bob API times out | SSE emits `error` event, dashboard shows manual review prompt |
| watsonx.ai unavailable | Keyword-based confidence fallback, logged in audit trail |
| StaticAnalysisAgent returns FAIL | Approve button hidden, Escalate Only shown, deployment blocked |
| Tests fail after fix | BobShell exits 1, audit logs failure, "Fix rejected — tests failed" on dashboard |
| Orchestrate pipeline timeout (>60s) | Backend routes directly to human approval, logs timeout |
| Memory does not recover after fix | /metrics poll detects this, "Monitoring — fix may be partial" shown |
| Second incident fires during active one | Queued in backend, processed after current incident closes |
| Missing env vars at startup | startup.sh fails immediately with exact variable name |
| Bob produces no code diff | Dashboard shows "Manual fix required", Approve button disabled |
| Runbook read fails | PostIncidentAgent proceeds without history context, logs warning |

---

## Governance — Human Always Decides

```
Bob diagnoses → watsonx.ai assesses risk → Granite validates →
Orchestrate agents verify → Human decides → BobShell executes
```

The Approve button appears only after all four agents complete. No code reaches any environment without a human clicking it. Every step — every agent verdict, every Bob reasoning phase, every deployment command — is logged in the BobShell audit trail with timestamps and provenance.

---

## Key Metrics

| Metric | Industry Average | OpsBob |
|---|---|---|
| MTTR | 3–4 hours | < 5 minutes |
| Time to diagnosis | 30–90 minutes | ~90 seconds |
| Engineers paged | 1–3 | 0 (review only) |
| Fix validation steps | 0–1 | 4 (static, tests, risk, routing) |
| Audit trail | Manual / partial | Complete, automated |

---

## Team

**DRAGORITHM** — IBM Bob Hackathon 2026
