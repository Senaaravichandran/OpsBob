// OpsBob Dashboard - Enterprise production intelligence platform with real-time incident monitoring
import { useState, useEffect } from 'react'
import './Dashboard.css'

const BACKEND_URL = 'http://localhost:8000'

function Dashboard() {
  const [incidents, setIncidents] = useState([])
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [analysis, setAnalysis] = useState({
    ask: { content: '', loading: false, complete: false },
    plan: { content: '', loading: false, complete: false },
    code: { content: '', loading: false, complete: false }
  })
  const [deploymentLogs, setDeploymentLogs] = useState([])
  const [memoryBefore, setMemoryBefore] = useState('340 MB')
  const [memoryAfter, setMemoryAfter] = useState('128 MB')
  const [showMemoryAfter, setShowMemoryAfter] = useState(false)
  const [isDeploying, setIsDeploying] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [deploymentComplete, setDeploymentComplete] = useState(false)
  const [mttr, setMttr] = useState('')
  const [incidentStartTime, setIncidentStartTime] = useState(null)
  const [systemStatus, setSystemStatus] = useState('nominal')

  // Fetch incidents on load - every 5 seconds
  useEffect(() => {
    fetchIncidents()
    const interval = setInterval(fetchIncidents, 5000)
    return () => clearInterval(interval)
  }, [])

  // Update system status based on incidents
  useEffect(() => {
    if (incidents.length > 0) {
      setSystemStatus('incident')
    } else {
      setSystemStatus('nominal')
    }
  }, [incidents])

  const fetchIncidents = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/incidents`)
      const data = await response.json()
      setIncidents(Object.values(data))
    } catch (error) {
      console.error('Error fetching incidents:', error)
    }
  }

  const analyzeIncident = async (incident) => {
    setSelectedIncident(incident)
    setAnalyzing(true)
    setDeploymentComplete(false)
    setShowMemoryAfter(false)
    setIncidentStartTime(Date.now())
    setDeploymentLogs([])
    
    setAnalysis({
      ask: { content: '', loading: true, complete: false },
      plan: { content: '', loading: false, complete: false },
      code: { content: '', loading: false, complete: false }
    })

    // Connect to SSE stream
    const eventSource = new EventSource(`${BACKEND_URL}/stream/${incident.incidentId}`)

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      if (data.phase === 'ask') {
        setAnalysis(prev => ({
          ...prev,
          ask: {
            content: prev.ask.content + data.content,
            loading: !data.done,
            complete: data.done
          }
        }))
        if (data.done) {
          setAnalysis(prev => ({
            ...prev,
            plan: { ...prev.plan, loading: true }
          }))
        }
      } else if (data.phase === 'plan') {
        setAnalysis(prev => ({
          ...prev,
          plan: {
            content: prev.plan.content + data.content,
            loading: !data.done,
            complete: data.done
          }
        }))
        if (data.done) {
          setAnalysis(prev => ({
            ...prev,
            code: { ...prev.code, loading: true }
          }))
        }
      } else if (data.phase === 'code') {
        setAnalysis(prev => ({
          ...prev,
          code: {
            content: prev.code.content + data.content,
            loading: !data.done,
            complete: data.done
          }
        }))
        if (data.done) {
          setAnalyzing(false)
        }
      } else if (data.phase === 'complete') {
        setAnalyzing(false)
        eventSource.close()
      }
    }

    eventSource.onerror = () => {
      setAnalyzing(false)
      eventSource.close()
    }
  }

  const approveFix = async () => {
    if (!selectedIncident) return

    try {
      await fetch(`${BACKEND_URL}/approve/${selectedIncident.incidentId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true })
      })

      setIsDeploying(true)
      setDeploymentLogs([])

      // Connect to deployment stream
      const eventSource = new EventSource(`${BACKEND_URL}/deploy-stream/${selectedIncident.incidentId}`)

      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data)
        
        if (data.type === 'log') {
          setDeploymentLogs(prev => [...prev, data])
        } else if (data.type === 'completion' && data.status === 'resolved') {
          // Calculate MTTR
          const endTime = Date.now()
          const durationMs = endTime - incidentStartTime
          const minutes = Math.floor(durationMs / 60000)
          const seconds = Math.floor((durationMs % 60000) / 1000)
          const mttrString = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
          
          setMttr(mttrString)
          setShowMemoryAfter(true)
          setIsDeploying(false)
          setDeploymentComplete(true)
          eventSource.close()
        }
      }

      eventSource.onerror = () => {
        eventSource.close()
        setIsDeploying(false)
      }
    } catch (error) {
      console.error('Error approving fix:', error)
      setIsDeploying(false)
    }
  }

  const escalateToHuman = () => {
    alert('Escalating to human engineer...')
  }

  const renderDiffLine = (line, index) => {
    if (line.startsWith('+')) {
      return <div key={index} className="diff-line diff-add">{line}</div>
    } else if (line.startsWith('-')) {
      return <div key={index} className="diff-line diff-remove">{line}</div>
    } else {
      return <div key={index} className="diff-line">{line}</div>
    }
  }

  const renderAnalysisContent = (content, phase) => {
    if (!content) return null
    
    if (phase === 'code') {
      const lines = content.split('\n')
      return (
        <div className="code-diff">
          {lines.map((line, i) => renderDiffLine(line, i))}
        </div>
      )
    }
    
    return <div className="analysis-text">{content}</div>
  }

  const getPhaseStatus = (phase) => {
    if (phase.complete) return 'COMPLETE'
    if (phase.loading) return 'PROCESSING'
    return 'PENDING'
  }

  const getPhaseStatusClass = (phase) => {
    if (phase.complete) return 'status-complete'
    if (phase.loading) return 'status-processing'
    return 'status-pending'
  }

  const formatLogMessage = (log) => {
    const msg = log.message
    if (msg.includes('✓')) return <span className="log-success">{msg}</span>
    if (msg.includes('✗')) return <span className="log-error">{msg}</span>
    if (msg.includes('IBM') || msg.includes('Cloud')) return <span className="log-deploy">{msg}</span>
    return <span className="log-normal">{msg}</span>
  }

  const allPhasesComplete = analysis.ask.complete && analysis.plan.complete && analysis.code.complete

  return (
    <div className="dashboard">
      {/* Header Bar */}
      <header className="dashboard-header">
        <div className="header-left">
          <img src="/logo.png" alt="OpsBob" className="header-logo" />
          <span className="header-title">OPSBOB</span>
        </div>
        <div className="header-center">
          PRODUCTION INTELLIGENCE PLATFORM
        </div>
        <div className="header-right">
          <div className="system-status">
            <span className={`status-dot ${systemStatus === 'nominal' ? 'status-nominal' : 'status-incident'}`}></span>
            <span className="status-label">
              {systemStatus === 'nominal' ? 'ALL SYSTEMS NOMINAL' : 'INCIDENT ACTIVE'}
            </span>
          </div>
          <span className="ibm-badge">IBM</span>
        </div>
      </header>

      {/* Three Panel Layout */}
      <div className="dashboard-content">
        {/* LEFT PANEL - Incident Feed */}
        <aside className="panel panel-left">
          <div className="panel-header">
            <span className="panel-title">LIVE INCIDENTS</span>
            {incidents.length > 0 && (
              <span className="incident-count">{incidents.length}</span>
            )}
          </div>
          
          <div className="incident-list">
            {incidents.length === 0 ? (
              <div className="empty-state">
                <span className="status-dot status-nominal"></span>
                <span className="empty-text">MONITORING ACTIVE</span>
              </div>
            ) : (
              incidents.map((incident) => (
                <div
                  key={incident.incidentId}
                  className={`incident-card ${selectedIncident?.incidentId === incident.incidentId ? 'selected' : ''}`}
                >
                  <div className="incident-header">
                    <span className="incident-service">{incident.service}</span>
                    <span className={`severity-badge severity-${incident.severity.toLowerCase()}`}>
                      {incident.severity}
                    </span>
                  </div>
                  <div className="incident-type">{incident.type}</div>
                  <div className="incident-time">
                    {new Date(incident.startTime || Date.now()).toLocaleTimeString()}
                  </div>
                  {incident.memory && (
                    <div className="incident-memory">Memory: {incident.memory}</div>
                  )}
                  <button
                    className="analyze-button"
                    onClick={() => analyzeIncident(incident)}
                  >
                    ANALYZE WITH BOB
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* CENTER PANEL - Bob Analysis */}
        <main className="panel panel-center">
          <div className="panel-header">
            <span className="panel-title">BOB ANALYSIS ENGINE</span>
          </div>

          {!selectedIncident ? (
            <div className="empty-analysis">
              <p>Select an incident to begin analysis</p>
            </div>
          ) : (
            <div className="analysis-container">
              {/* ASK Phase */}
              <div className="analysis-block">
                <div className="analysis-block-header">
                  <div className="phase-info">
                    <span className="phase-icon">🔍</span>
                    <span className="phase-name">ASK PHASE</span>
                  </div>
                  <span className={`phase-status ${getPhaseStatusClass(analysis.ask)}`}>
                    {getPhaseStatus(analysis.ask)}
                  </span>
                </div>
                <div className="analysis-content ask-phase">
                  {renderAnalysisContent(analysis.ask.content || 'Analyzing source code...', 'ask')}
                </div>
              </div>

              {/* PLAN Phase */}
              <div className="analysis-block">
                <div className="analysis-block-header">
                  <div className="phase-info">
                    <span className="phase-icon">📋</span>
                    <span className="phase-name">PLAN PHASE</span>
                  </div>
                  <span className={`phase-status ${getPhaseStatusClass(analysis.plan)}`}>
                    {getPhaseStatus(analysis.plan)}
                  </span>
                </div>
                <div className="analysis-content plan-phase">
                  {renderAnalysisContent(analysis.plan.content || 'Identifying root cause...', 'plan')}
                </div>
              </div>

              {/* CODE Phase */}
              <div className="analysis-block">
                <div className="analysis-block-header">
                  <div className="phase-info">
                    <span className="phase-icon">💻</span>
                    <span className="phase-name">CODE PHASE</span>
                  </div>
                  <span className={`phase-status ${getPhaseStatusClass(analysis.code)}`}>
                    {getPhaseStatus(analysis.code)}
                  </span>
                </div>
                <div className="analysis-content code-phase">
                  {renderAnalysisContent(analysis.code.content || 'Generating fix...', 'code')}
                </div>
              </div>

              {/* Analysis Complete Banner */}
              {allPhasesComplete && !deploymentComplete && (
                <div className="analysis-complete">
                  BOB ANALYSIS COMPLETE
                </div>
              )}
            </div>
          )}
        </main>

        {/* RIGHT PANEL - Command & Control */}
        <aside className="panel panel-right">
          {/* Action Buttons */}
          <div className="action-section">
            <div className="section-title">RESPONSE ACTIONS</div>
            <button
              className="action-button approve-button"
              onClick={approveFix}
              disabled={!allPhasesComplete || isDeploying || deploymentComplete}
            >
              APPROVE & DEPLOY FIX
            </button>
            <div className="approval-note">HUMAN APPROVAL REQUIRED</div>
            <button
              className="action-button escalate-button"
              onClick={escalateToHuman}
              disabled={isDeploying}
            >
              ESCALATE TO HUMAN
            </button>
          </div>

          {/* BobShell Audit Log */}
          <div className="audit-section">
            <div className="section-title">BOBSHELL AUDIT TRAIL</div>
            <div className="audit-log">
              {deploymentLogs.length === 0 ? (
                <div className="log-empty">Waiting for deployment...</div>
              ) : (
                deploymentLogs.map((log, i) => (
                  <div key={i} className="log-entry">
                    <span className="log-timestamp">
                      [{new Date(log.timestamp).toLocaleTimeString()}]
                    </span>{' '}
                    {formatLogMessage(log)}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Memory Telemetry */}
          <div className="telemetry-section">
            <div className="section-title">MEMORY TELEMETRY</div>
            <div className="telemetry-stats">
              <div className="stat-box stat-before">
                <div className="stat-label">BEFORE</div>
                <div className="stat-value">{memoryBefore}</div>
                <div className="stat-status status-degraded">DEGRADED</div>
              </div>
              {showMemoryAfter && (
                <div className="stat-box stat-after">
                  <div className="stat-label">AFTER</div>
                  <div className="stat-value">{memoryAfter}</div>
                  <div className="stat-status status-nominal-text">NOMINAL</div>
                </div>
              )}
            </div>
          </div>

          {/* MTTR Display */}
          {deploymentComplete && (
            <div className="mttr-section">
              <div className="mttr-label">MEAN TIME TO RESOLUTION</div>
              <div className="mttr-value">{mttr}</div>
              <div className="mttr-footer">INCIDENT RESOLVED BY IBM BOB</div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

export default Dashboard

// Made with Bob
