# OpsBob - Autonomous Production Intelligence Platform

## 🎯 Project Overview

**OpsBob** is an AI-powered Site Reliability Engineering (SRE) assistant that autonomously detects, analyzes, and resolves production incidents in real-time. Built with IBM's Bob AI orchestrator, it transforms incident response from a manual, time-consuming process into an automated, intelligent workflow.

### The Problem We Solve

Traditional incident response requires:
- Manual code analysis (30-60 minutes)
- Root cause identification by senior engineers
- Writing and testing fixes
- Deployment coordination
- Post-deployment monitoring

**OpsBob reduces this to 4-5 minutes with zero human intervention until approval.**

### What Makes OpsBob Special

1. **Autonomous Analysis**: Bob reads your actual source code and identifies the exact root cause
2. **Intelligent Fixes**: Generates surgical code patches with unit tests
3. **One-Click Deployment**: Deploys fixes to IBM Cloud Code Engine automatically
4. **Enterprise UI**: World-class dashboard that looks like a mission control center
5. **Real-time Streaming**: Watch Bob think and work in real-time via Server-Sent Events

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION SYSTEM                         │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │ Payments API │ ◄─────► │   Instana    │                 │
│  │ (Node.js)    │         │  Monitoring  │                 │
│  └──────────────┘         └──────┬───────┘                 │
└────────────────────────────────────┼──────────────────────────┘
                                     │ Webhook
                                     ▼
┌─────────────────────────────────────────────────────────────┐
│                      OPSBOB SYSTEM                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              FRONTEND (React + Vite)                   │ │
│  │  ┌──────────────┐    ┌──────────────────────────────┐ │ │
│  │  │   Landing    │───►│       Dashboard              │ │ │
│  │  │   Page       │    │  ┌────────┬────────┬────────┐│ │ │
│  │  │  (Cinematic) │    │  │Incident│Analysis│Command ││ │ │
│  │  └──────────────┘    │  │  Feed  │ Engine │Control ││ │ │
│  │                      │  └────────┴────────┴────────┘│ │ │
│  └──────────────────────┴──────────────────────────────┘ │ │
│                              │ SSE Streams                  │
│                              ▼                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           BACKEND (FastAPI + Python)                   │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │ │
│  │  │   Webhook    │  │  Bob Client  │  │  BobShell   │ │ │
│  │  │   Handler    │─►│  (3 Phases)  │─►│  Deployer   │ │ │
│  │  └──────────────┘  └──────┬───────┘  └─────────────┘ │ │
│  └────────────────────────────┼────────────────────────────┘ │
└────────────────────────────────┼──────────────────────────────┘
                                 │ API Calls
                                 ▼
                    ┌────────────────────────┐
                    │   IBM Bob AI API       │
                    │  (bob-orchestrator)    │
                    └────────────────────────┘
```

---

## 🚀 How It Works

### Step 1: Incident Detection
```
Instana detects memory leak → Sends webhook to OpsBob
```

### Step 2: Bob's Three-Phase Analysis

#### Phase 1: ASK (Code Reading)
```
Bob reads the actual source code:
- Identifies memory management patterns
- Finds data structures that could grow unbounded
- Locates caching mechanisms without cleanup
```

#### Phase 2: PLAN (Root Cause Analysis)
```
Bob identifies the exact problem:
- Names the specific variable causing the leak
- Pinpoints the line number
- Explains why it leaks
- Proposes a 3-point fix plan
```

#### Phase 3: CODE (Fix Generation)
```
Bob generates:
- Unified diff patch (surgical changes only)
- Unit test to prevent regression
- Minimal, production-ready code
```

### Step 3: Human Approval
```
Engineer reviews Bob's analysis and fix
Clicks "APPROVE & DEPLOY FIX" button
```

### Step 4: Automated Deployment (BobShell)
```
1. Apply patch to source code
2. Run test suite
3. Build Docker image
4. Push to IBM Cloud Container Registry
5. Deploy to Code Engine
6. Health check verification
7. Report MTTR (Mean Time To Resolution)
```

---

## 💻 Technology Stack

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **IBM Plex Mono** - Typography
- **Custom CSS** - No component library, pure enterprise design
- **Server-Sent Events (SSE)** - Real-time streaming

### Backend
- **FastAPI** - Python web framework
- **Uvicorn** - ASGI server
- **aiohttp** - Async HTTP client for Bob API
- **python-dotenv** - Environment configuration

### AI/ML
- **IBM Bob Orchestrator** - Multi-mode AI assistant
- **Three-phase analysis** - Ask → Plan → Code
- **Conversation context** - Maintains context across phases

### Infrastructure
- **IBM Cloud Code Engine** - Serverless container platform
- **IBM Cloud Container Registry** - Docker image storage
- **Instana** - Application Performance Monitoring

---

## 📁 Project Structure

```
opsbob/
├── frontend/                    # React dashboard
│   ├── public/
│   │   └── logo.png            # OpsBob logo
│   ├── src/
│   │   ├── Landing.jsx         # Cinematic entry page
│   │   ├── Landing.css         # Landing page styles
│   │   ├── Dashboard.jsx       # Main dashboard (3-panel layout)
│   │   ├── Dashboard.css       # Dashboard styles
│   │   ├── App.jsx             # Root component (state management)
│   │   ├── main.jsx            # React entry point
│   │   └── index.css           # Global styles
│   ├── index.html              # HTML template
│   ├── package.json            # Dependencies
│   └── vite.config.js          # Vite configuration
│
├── backend/                     # FastAPI server
│   ├── main.py                 # API endpoints & SSE streaming
│   ├── bob_client.py           # IBM Bob API integration
│   ├── bobshell.py             # Deployment orchestrator
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Environment variables
│
├── demo-service/                # Simulated production service
│   ├── server.js               # Node.js API with memory leak
│   ├── load-generator.js       # Traffic simulator
│   ├── package.json            # Dependencies
│   └── Dockerfile              # Container definition
│
├── mcp-server/                  # Model Context Protocol server
│   ├── src/
│   │   └── index.ts            # MCP implementation
│   ├── package.json            # Dependencies
│   └── tsconfig.json           # TypeScript config
│
├── .env.example                 # Environment template
├── ARCHITECTURE.md              # System architecture docs
├── demo-trigger.sh              # Demo incident trigger script
├── stop-demo.sh                 # Demo cleanup script
└── readmefileclaude.md         # This file
```

---

## 🎨 Frontend Design

### Landing Page
- **Pure black background** (#000000)
- **Glowing logo** with drop-shadow effect
- **Pulsing red status indicator** - "SYSTEM ONLINE"
- **Smooth fade transition** (600ms) to dashboard
- **Cinematic feel** - Looks like a sci-fi movie interface

### Dashboard (Three-Panel Layout)

#### Left Panel - Incident Feed (300px)
- Live incident cards with severity badges
- Color-coded borders (RED: HIGH, AMBER: MEDIUM)
- "ANALYZE WITH BOB" buttons
- Empty state: "MONITORING ACTIVE" with green dot

#### Center Panel - Bob Analysis Engine (flexible width)
- Three analysis blocks (Ask, Plan, Code)
- Phase status badges (PENDING, PROCESSING, COMPLETE)
- Color-coded borders:
  - Ask Phase: Blue (#4488ff)
  - Plan Phase: Amber (#ffaa00)
  - Code Phase: Green (#00ff88)
- Code diff rendering (green additions, red deletions)
- "BOB ANALYSIS COMPLETE" banner

#### Right Panel - Command & Control (320px)
- **Action Buttons:**
  - "APPROVE & DEPLOY FIX" (green, disabled until analysis complete)
  - "ESCALATE TO HUMAN" (red border)
- **BobShell Audit Trail:**
  - Real-time deployment logs
  - Color-coded messages (success: green, error: red, deploy: blue)
- **Memory Telemetry:**
  - Before: 340 MB (DEGRADED - red)
  - After: 128 MB (NOMINAL - green)
- **MTTR Display:**
  - Large monospace timer
  - "INCIDENT RESOLVED BY IBM BOB" footer

### Color Scheme
```css
Background:     #0a0a0a (near black)
Panels:         #111111
Borders:        #1e1e1e
Alerts:         #ff4444 (red)
Success:        #00ff88 (bright green)
Text Primary:   #ffffff
Text Secondary: #888888
```

---

## 🔧 Backend Implementation

### API Endpoints

#### POST /webhook
Receives incident alerts from Instana
```json
{
  "service": "payments-api",
  "severity": "HIGH",
  "type": "MEMORY_LEAK",
  "incidentId": "INC-1234567890"
}
```

#### GET /stream/{incidentId}
Streams Bob's analysis via Server-Sent Events
```
data: {"phase": "ask", "content": "...", "done": false}
data: {"phase": "plan", "content": "...", "done": false}
data: {"phase": "code", "content": "...", "done": true}
data: {"phase": "complete", "content": "", "done": true}
```

#### POST /approve/{incidentId}
Approves or rejects Bob's proposed fix
```json
{
  "approved": true
}
```

#### GET /deploy-stream/{incidentId}
Streams deployment progress via SSE
```
data: {"type": "log", "message": "Applying patch...", "timestamp": "..."}
data: {"type": "completion", "status": "resolved", "incidentId": "..."}
```

#### GET /incidents
Returns all active incidents
```json
{
  "INC-123": {
    "service": "payments-api",
    "severity": "HIGH",
    "status": "received"
  }
}
```

### Bob API Integration

**Three Sequential Calls:**

1. **ASK Phase** - Code reading and analysis
2. **PLAN Phase** - Root cause identification (includes Ask context)
3. **CODE Phase** - Fix generation (includes Ask + Plan context)

**API Format:**
```python
POST https://api.bob.ibm.com/v1/generate
Headers:
  Authorization: Bearer {BOB_API_KEY}
  Content-Type: application/json

Body:
{
  "model": "bob-orchestrator",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_tokens": 500
}
```

### BobShell Deployment Steps

1. Apply diff patch to server.js
2. Run npm test
3. Build Docker image
4. Push to IBM Cloud Container Registry
5. Update Code Engine application
6. Health check verification
7. Report MTTR

---

## 🚦 Setup & Installation

### Prerequisites
- Node.js 18+
- Python 3.9+
- IBM Cloud account
- IBM Bob API key

### Environment Variables

Create `.env` file in backend directory:
```bash
# IBM Bob API
BOB_API_KEY=your_bob_api_key_here

# IBM Cloud
IBM_CLOUD_API_KEY=your_ibm_cloud_key
IBM_CLOUD_REGION=jp-tok
CODE_ENGINE_PROJECT=opsbob-demo
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:3001
```

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
# Runs on http://localhost:8000
```

### Demo Service Setup
```bash
cd demo-service
npm install
npm start
# Runs on http://localhost:3002
```

---

## 🎬 Running a Demo

### 1. Start All Services
```bash
# Terminal 1 - Backend
cd backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev

# Terminal 3 - Demo Service
cd demo-service
npm start
```

### 2. Open Dashboard
Navigate to http://localhost:3001

### 3. Trigger Incident
```bash
# Use the demo trigger script
./demo-trigger.sh

# Or manually via curl
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "service": "payments-api",
    "severity": "HIGH",
    "type": "MEMORY_LEAK",
    "incidentId": "INC-'$(date +%s)'"
  }'
```

### 4. Watch Bob Work
1. Incident appears in left panel
2. Click "ANALYZE WITH BOB"
3. Watch three-phase analysis stream in real-time
4. Review the proposed fix
5. Click "APPROVE & DEPLOY FIX"
6. Watch deployment logs in audit trail
7. See MTTR displayed on completion

---

## 📊 Key Metrics

### Performance
- **Analysis Time**: 15-30 seconds (3 Bob API calls)
- **Deployment Time**: 2-3 minutes (build + deploy)
- **Total MTTR**: 4-5 minutes (vs 30-60 minutes manual)
- **Accuracy**: Depends on Bob's training and code quality

### Cost Savings
- **Engineer Time**: 55 minutes saved per incident
- **Downtime Reduction**: 90%+ faster resolution
- **Consistency**: Same quality fix every time

---

## 🔒 Security Considerations

1. **API Keys**: Stored in .env, never committed to git
2. **Human Approval**: Required before any deployment
3. **Audit Trail**: Every action logged with timestamp
4. **Rollback**: Automatic rollback on health check failure
5. **Code Review**: Bob's fixes are visible before deployment

---

## 🎯 Use Cases

### 1. Memory Leaks
- Unbounded caches
- Event listener accumulation
- Circular references

### 2. Performance Issues
- N+1 queries
- Missing indexes
- Inefficient algorithms

### 3. Configuration Errors
- Wrong timeouts
- Missing rate limits
- Incorrect connection pools

### 4. Logic Bugs
- Off-by-one errors
- Race conditions
- Edge case handling

---

## 🚀 Future Enhancements

1. **Multi-Service Support**: Analyze multiple services simultaneously
2. **Predictive Analysis**: Detect issues before they become incidents
3. **Learning Loop**: Bob learns from approved/rejected fixes
4. **Integration Hub**: Connect to Slack, PagerDuty, Jira
5. **Custom Runbooks**: Define service-specific fix patterns
6. **A/B Testing**: Deploy fixes to canary environments first

---

## 🤝 Contributing

This is a demonstration project showcasing IBM Bob's capabilities. For production use:

1. Add comprehensive error handling
2. Implement authentication/authorization
3. Add database for incident history
4. Create monitoring dashboards
5. Set up CI/CD pipelines
6. Add integration tests

---

## 📝 License

This project is a demonstration of IBM Bob AI capabilities. Contact IBM for production licensing.

---

## 🙏 Acknowledgments

- **IBM Bob Team** - For the incredible AI orchestrator
- **IBM Cloud** - For Code Engine and Container Registry
- **Instana** - For application monitoring
- **React Team** - For the amazing UI framework
- **FastAPI Team** - For the excellent Python framework

---

## 📞 Support

For questions about:
- **IBM Bob API**: Contact IBM Bob support
- **IBM Cloud**: Contact IBM Cloud support
- **This Demo**: Review the code and documentation

---

## 🎓 Learning Resources

- [IBM Bob Documentation](https://ibm.com/bob)
- [IBM Cloud Code Engine](https://cloud.ibm.com/docs/codeengine)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [React Documentation](https://react.dev)
- [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

---

**Built with ❤️ by the OpsBob Team**

*Transforming incident response from reactive to proactive, one AI-powered fix at a time.*