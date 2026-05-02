# OpsBob - AI-Powered SRE Assistant

OpsBob is an autonomous Site Reliability Engineering (SRE) assistant that detects production incidents, diagnoses root causes, generates fixes, and deploys them automatically—all powered by IBM's AI and cloud technologies. When a memory leak is detected in a production service, OpsBob analyzes the codebase, identifies the exact bug location, proposes a fix with unit tests, and deploys it to IBM Cloud Code Engine, reducing Mean Time To Resolution (MTTR) from hours to minutes.

## How to Run the Demo

### Prerequisites
- Node.js 18+ and npm
- Python 3.9+ and pip
- IBM Cloud account (for production deployment)

### Step 1: Install Dependencies

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cd ..
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

**Demo Service:**
```bash
cd demo-service
npm install
cd ..
```

**MCP Server:**
```bash
cd mcp-server
npm install
npm run build
cd ..
```

### Step 2: Configure Environment Variables

Create a `.env` file in the root directory:

```env
BOB_API_KEY=your_ibm_bob_api_key_here
BOB_API_URL=https://api.bob.ibm.com
IBM_CLOUD_REGION=us-south
CODE_ENGINE_PROJECT=opsbob-demo
```

### Step 3: Start the Backend

```bash
cd backend
uvicorn main:app --reload
```

The FastAPI backend will start on `http://localhost:8000`

### Step 4: Start the Frontend

In a new terminal:

```bash
cd frontend
npm run dev
```

The React dashboard will start on `http://localhost:3000`

### Step 5: Trigger the Demo

In a new terminal:

```bash
bash demo-trigger.sh
```

This script will:
1. Start the demo payments-api service
2. Start the load generator (simulates traffic)
3. Trigger a mock incident webhook
4. Display the dashboard URL

**Open http://localhost:3000 to watch OpsBob in action!**

### Stop the Demo

```bash
bash stop-demo.sh
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         OpsBob System                            │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   Instana    │  (Monitoring & Alerting)
    │  Mock/Real   │
    └──────┬───────┘
           │ Webhook
           ▼
    ┌──────────────┐
    │   FastAPI    │  (Orchestration Layer)
    │   Backend    │  - Incident Management
    │              │  - SSE Streaming
    └──────┬───────┘
           │
           ├─────────────────┐
           │                 │
           ▼                 ▼
    ┌──────────────┐  ┌──────────────┐
    │  IBM Bob API │  │    BobShell  │
    │              │  │              │
    │ - Code Read  │  │ - Apply Fix  │
    │ - Diagnosis  │  │ - Run Tests  │
    │ - Fix Gen    │  │ - Deploy     │
    └──────┬───────┘  └──────┬───────┘
           │                 │
           │                 ▼
           │          ┌──────────────┐
           │          │ IBM Cloud    │
           │          │ Code Engine  │
           │          │              │
           │          │ - Container  │
           │          │ - Auto-scale │
           │          └──────────────┘
           │
           ▼
    ┌──────────────┐
    │    React     │  (Dashboard)
    │  Dashboard   │  - IBM Carbon Design
    │              │  - Real-time Updates
    │              │  - Audit Trail
    └──────────────┘
```

## IBM Technologies Used

OpsBob leverages six key IBM technologies:

### 1. **IBM Bob (AI Assistant)**
- Multi-phase code analysis (Ask, Plan, Code)
- Natural language understanding of incidents
- Automated fix generation with unit tests
- Context-aware code modifications

### 2. **IBM Cloud Code Engine**
- Serverless container deployment
- Automatic scaling based on load
- Zero-downtime deployments
- Built-in monitoring and logging

### 3. **IBM Instana (Monitoring)**
- Real-time application performance monitoring
- Automatic incident detection
- Stack trace collection
- Memory leak identification

### 4. **IBM Carbon Design System**
- Enterprise-grade React components
- Dark theme optimized for operations
- Accessible UI patterns
- Consistent design language

### 5. **Model Context Protocol (MCP)**
- Standardized AI tool integration
- Structured incident data exchange
- Real-time streaming capabilities
- Extensible tool framework

### 6. **IBM Cloud Container Registry**
- Secure container image storage
- Vulnerability scanning
- Global image distribution
- Integration with Code Engine

## Project Structure

```
opsbob/
├── backend/                 # FastAPI orchestration layer
│   ├── main.py             # API endpoints & SSE streaming
│   ├── bob_client.py       # IBM Bob API integration
│   ├── bobshell.py         # Deployment automation
│   └── requirements.txt    # Python dependencies
├── frontend/               # React dashboard
│   ├── src/
│   │   ├── App.jsx        # Main dashboard component
│   │   ├── App.css        # Styles
│   │   └── main.jsx       # Entry point
│   ├── package.json       # Node dependencies
│   └── vite.config.js     # Vite configuration
├── demo-service/          # Mock payments API
│   ├── server.js          # Express server with memory leak
│   ├── load-generator.js  # Traffic simulator
│   └── Dockerfile         # Container definition
├── mcp-server/            # Model Context Protocol server
│   ├── src/index.ts       # MCP tools implementation
│   ├── package.json       # TypeScript dependencies
│   └── README.md          # MCP documentation
├── demo-trigger.sh        # One-command demo starter
├── stop-demo.sh           # Demo cleanup script
└── README.md              # This file
```

## Demo Flow

1. **Incident Detection** (0:00)
   - Load generator causes memory leak in payments-api
   - Instana detects threshold breach
   - Webhook fires to OpsBob backend

2. **Bob Analysis** (0:05 - 1:30)
   - **Ask Phase**: Reads server.js, identifies sessionCache
   - **Plan Phase**: Diagnoses unbounded Map growth
   - **Code Phase**: Generates fix with TTL and cleanup

3. **Human Approval** (1:30 - 1:45)
   - Engineer reviews proposed fix in dashboard
   - Clicks "✓ Approve Fix" button

4. **Automated Deployment** (1:45 - 4:00)
   - BobShell applies fix to source code
   - Runs smoke tests
   - Builds Docker container
   - Deploys to Code Engine
   - Monitors for stability

5. **Resolution** (4:00)
   - Memory drops from 340MB to 128MB
   - Toast notification: "Incident Resolved by OpsBob"
   - MTTR: ~4 minutes

## Key Features

- ✅ **Autonomous Operation**: Zero-touch incident resolution
- ✅ **Real-Time Streaming**: Live updates via Server-Sent Events
- ✅ **Multi-Phase Analysis**: Structured problem-solving approach
- ✅ **Human-in-the-Loop**: Optional approval gate for safety
- ✅ **Audit Trail**: Complete deployment log with timestamps
- ✅ **MTTR Tracking**: Automatic calculation of resolution time
- ✅ **Demo Mode**: One-click incident trigger for presentations

## Development

### Running Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

### Building for Production

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm run build

# MCP Server
cd mcp-server
npm run build
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOB_API_KEY` | IBM Bob API authentication token | Yes |
| `BOB_API_URL` | IBM Bob API endpoint | Yes |
| `IBM_CLOUD_REGION` | IBM Cloud region (e.g., us-south) | Yes |
| `CODE_ENGINE_PROJECT` | Code Engine project name | Yes |

## Troubleshooting

**Backend won't start:**
- Check Python version: `python --version` (needs 3.9+)
- Verify dependencies: `pip list | grep fastapi`

**Frontend won't connect:**
- Ensure backend is running on port 8000
- Check browser console for CORS errors
- Verify Vite proxy configuration

**Demo trigger fails:**
- Confirm backend is running: `curl http://localhost:8000/health`
- Check if ports 3001 (demo-service) and 8000 (backend) are available

## License

MIT

## Contributors

Built for the IBM Hackathon 2024 - AI-Powered SRE Track