import React, { useState, useEffect, useCallback } from 'react'
import { Tag, Button } from '@carbon/react'
import { Activity, IbmCloud, Bot } from '@carbon/icons-react'
import Lottie from 'lottie-react'
import chatbotAnimation from '../public/Chatbot.json'

import IncidentFeed from './components/IncidentFeed'
import DiagnosisCard from './components/DiagnosisCard'
import RiskAssessmentCard from './components/RiskAssessmentCard'
import OrchestrationFlowCard from './components/OrchestrationFlowCard'
import AgentPipelineStatus from './components/AgentPipelineStatus'
import OrchestratePanel from './components/OrchestratePanel'
import FixActions from './components/FixActions'
import AuditTrail from './components/AuditTrail'
import MemoryTelemetry from './components/MemoryTelemetry'
import SystemHealthBar from './components/SystemHealthBar'
import DemoServiceLogs from './components/DemoServiceLogs'
import './Dashboard.css'

const AGENT_LABELS = {
  static_analysis: 'Static Analysis',
  test_runner: 'Test Runner',
  approval_router: 'Approval Router'
}

function summarizeAgentResult(result) {
  if (!result) return ''
  if (Array.isArray(result.findings) && result.findings.length > 0) {
    return result.findings.slice(0, 2).join(' ')
  }
  if (result.routing_reason) return result.routing_reason
  if (typeof result.report === 'string') return result.report
  if (typeof result.error === 'string') return result.error
  if (typeof result.summary === 'string') return result.summary
  if (typeof result.stdout === 'string') return result.stdout
  return ''
}

function Dashboard() {
  const [incidents, setIncidents] = useState({})
  const [activeIncidentId, setActiveIncidentId] = useState(null)
  const [phases, setPhases] = useState({ ask: '', plan: '', code: '' })
  const [currentPhase, setCurrentPhase] = useState(null)
  const [riskAssessment, setRiskAssessment] = useState(null)
  const [agentResults, setAgentResults] = useState({})
  const [pipelineComplete, setPipelineComplete] = useState(false)
  const [pipelineResults, setPipelineResults] = useState(null)
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const [analysisError, setAnalysisError] = useState(null)
  const [orchestrateDecision, setOrchestrateDecision] = useState(null)
  const [orchestrateStatus, setOrchestrateStatus] = useState(null)

  // ── IBM watsonx Orchestrate direct pipeline state ──
  const [centerMode, setCenterMode] = useState('bob')             // 'bob' | 'orchestrate'
  const [orchState, setOrchState] = useState('idle')              // idle | running | complete | error
  const [orchAgentResults, setOrchAgentResults] = useState({})
  const [orchCommanderText, setOrchCommanderText] = useState('')
  const [orchDecision, setOrchDecision] = useState('')
  const [orchElapsed, setOrchElapsed] = useState(0)
  const [orchProgressMsg, setOrchProgressMsg] = useState('')
  const [orchIncidentId, setOrchIncidentId] = useState(null)
  const [executionFeed, setExecutionFeed] = useState([])
  const [deploying, setDeploying] = useState(false)
  const [resolved, setResolved] = useState(false)
  const [deployLogs, setDeployLogs] = useState([])
  const [memBefore, setMemBefore] = useState(null)
  const [memAfter, setMemAfter] = useState(null)
  const [mttr, setMttr] = useState(null)
  const [systemStatus, setSystemStatus] = useState('nominal')

  const appendExecutionEvent = useCallback((entry) => {
    if (!entry?.message && !entry?.detail) return

    setExecutionFeed(prev => ([
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        timestamp: new Date().toISOString(),
        ...entry
      }
    ].slice(-18)))
  }, [])

  // ── IBM watsonx Orchestrate direct pipeline ──────────────────
  const handleOrchestrateRun = useCallback((incidentId) => {
    setOrchIncidentId(incidentId)
    setCenterMode('orchestrate')
    setOrchState('running')
    setOrchAgentResults({})
    setOrchCommanderText('')
    setOrchDecision('')
    setOrchElapsed(0)
    setOrchProgressMsg('')

    const es = new EventSource(`/orchestrate/stream/${incidentId}`)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.phase === 'progress') {
          setOrchElapsed(data.elapsed)
          setOrchProgressMsg(data.message)
        } else if (data.phase === 'agent_result') {
          setOrchAgentResults(prev => ({ ...prev, [data.agent]: data.result }))
        } else if (data.phase === 'complete') {
          setOrchCommanderText(data.commander_text || '')
          setOrchDecision(data.decision || '')
          setOrchState('complete')
          es.close()
        } else if (data.phase === 'error') {
          setOrchState('error')
          es.close()
        }
      } catch { /* ignore parse errors */ }
    }
    es.onerror = () => { setOrchState('error'); es.close() }
  }, [])

  // Poll for incidents
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch('/incidents')
        if (res.ok) {
          const data = await res.json()
          setIncidents(data)
          // Update system status
          const hasActive = Object.values(data).some(i => ['received', 'analyzing', 'deploying'].includes(i.status))
          setSystemStatus(hasActive ? 'incident' : 'nominal')
        }
      } catch { /* silent */ }
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => clearInterval(interval)
  }, [])

  // Analyze with Bob
  const handleAnalyze = useCallback((incidentId) => {
    setActiveIncidentId(incidentId)
    setPhases({ ask: '', plan: '', code: '' })
    setCurrentPhase('ask')
    setRiskAssessment(null)
    setAgentResults({})
    setPipelineComplete(false)
    setPipelineResults(null)
    setAnalysisComplete(false)
    setAnalysisError(null)
    setOrchestrateDecision(null)
    setOrchestrateStatus(null)
    setExecutionFeed([])
    setDeploying(false)
    setResolved(false)
    setDeployLogs([])
    setMemBefore(null)
    setMemAfter(null)
    setMttr(null)

    const eventSource = new EventSource(`/stream/${incidentId}`)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // Bob phases
        if (['ask', 'plan', 'code'].includes(data.phase)) {
          setCurrentPhase(data.phase)
          if (data.content) {
            setPhases(prev => ({
              ...prev,
              [data.phase]: (prev[data.phase] || '') + data.content
            }))
          }
          if (data.done && data.phase === 'plan' && data.risk_assessment) {
            setRiskAssessment(data.risk_assessment)
            const mem = data.risk_assessment?.blast_radius
            if (incidents[incidentId]?.mem_growth_mb) {
              setMemBefore(Math.round(incidents[incidentId].mem_growth_mb + 50))
            } else {
              setMemBefore(340)
            }
          }
          if (data.done && data.phase === 'code') {
            setPhases(prev => ({ ...prev, code: data.content || prev.code }))
          }
        }

        // Agent pipeline events
        if (data.phase === 'agent') {
          const nextResult = data.result || { status: data.status, verdict: data.status }
          setAgentResults(prev => ({
            ...prev,
            [data.agent]: nextResult
          }))
          appendExecutionEvent({
            actor: AGENT_LABELS[data.agent] || data.agent,
            status: data.status,
            message: data.message || 'Agent update received',
            detail: summarizeAgentResult(data.result)
          })
        }

        // Pipeline complete
        if (data.phase === 'pipeline_complete') {
          setPipelineComplete(true)
          setPipelineResults(data)
          setAnalysisComplete(true)
          setAnalysisError(null)
          setCurrentPhase(null)
          appendExecutionEvent({
            actor: 'Verification Pipeline',
            status: data.verdict,
            message: data.routing_reason
              ? `Pipeline verdict: ${String(data.verdict || 'review').toUpperCase()} — ${data.routing_reason}`
              : `Pipeline verdict: ${String(data.verdict || 'review').toUpperCase()}`
          })
          // Keep stream open — Orchestrate decision follows
        }

        if (data.phase === 'orchestrate_status') {
          setOrchestrateStatus(data.status)
          appendExecutionEvent({
            actor: 'Orchestrate Commander',
            status: data.status,
            message: data.message || 'Commander review in progress'
          })
        }

        // Orchestrate commander decision
        if (data.phase === 'orchestrate_decision') {
          setOrchestrateDecision(data)
          setOrchestrateStatus(data.decision)
          appendExecutionEvent({
            actor: 'Orchestrate Commander',
            status: data.decision,
            message: !data.orchestrate_used && data.error
              ? `Fallback decision: ${String(data.decision || 'review').toUpperCase()} — ${data.error}`
              : `Decision: ${String(data.decision || 'review').toUpperCase()}`
          })
          if (!data.orchestrate_used && data.error) {
            console.warn('[Orchestrate] fallback:', data.error)
          }
        }

        // Orchestrate auto-approved — close stream and start deploy immediately
        if (data.phase === 'auto_deploy') {
          appendExecutionEvent({
            actor: 'Orchestrate Commander',
            status: 'complete',
            message: 'Auto-deploy triggered for production rollout'
          })
          eventSource.close()
          handleAutoDeployStream(data.incidentId)
        }

        // Complete (no pipeline) — analysis only
        if (data.phase === 'complete' || (data.done && data.phase === 'code' && !data.agent)) {
          // Will wait for pipeline events
        }

        // Close stream after orchestrate decision when not auto-deploying
        if (data.phase === 'orchestrate_decision' && data.done) {
          const dec = data.decision
          if (dec !== 'approve') {
            eventSource.close()
          }
        }

        // Error
        if (data.phase === 'error') {
          setCurrentPhase(null)
          setAnalysisError(data.content || 'Analysis failed')
          setAnalysisComplete(false)
          setPipelineComplete(false)
          setPipelineResults(null)
          eventSource.close()
          console.error('Analysis error:', data.content)
        }
      } catch (e) {
        console.error('Parse error:', e)
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      if (!analysisComplete && !analysisError) {
        setAnalysisError('Analysis stream disconnected unexpectedly')
        setCurrentPhase(null)
      }
    }
  }, [analysisComplete, analysisError, appendExecutionEvent, incidents]) // eslint-disable-line react-hooks/exhaustive-deps

  // Called automatically when Orchestrate commander approves
  const handleAutoDeployStream = useCallback(async (incidentId) => {
    setDeploying(true)
    setDeployLogs(prev => [...prev, {
      type: 'info',
      message: '[Orchestrate Commander] Auto-approved — deploying to production',
      timestamp: new Date().toISOString()
    }])

    const eventSource = new EventSource(`/deploy-stream/${incidentId}`)
    const startTime = Date.now()

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'log') setDeployLogs(prev => [...prev, data])
        if (data.type === 'git_push') setDeployLogs(prev => [...prev, data])
        if (data.type === 'completion') {
          const elapsed = Math.round((Date.now() - startTime) / 1000)
          const mins = Math.floor(elapsed / 60)
          const secs = elapsed % 60
          setMttr(`${mins}m ${secs}s`)
          setMemAfter(data.memoryAfter ? parseInt(data.memoryAfter) : 128)
          setResolved(true)
          setDeploying(false)
          eventSource.close()
        }
        if (data.type === 'agent') {
          setDeployLogs(prev => [...prev, {
            type: 'agent',
            message: `[${data.agent}] ${data.status}`,
            timestamp: new Date().toISOString()
          }])
        }
        if (data.type === 'error') {
          setDeployLogs(prev => [...prev, { ...data, type: 'error' }])
          setDeploying(false)
          eventSource.close()
        }
      } catch (e) { console.error('Auto-deploy parse error:', e) }
    }
    eventSource.onerror = () => { eventSource.close(); setDeploying(false) }
  }, [])

  // Approve and deploy
  const handleApprove = useCallback(async () => {
    if (!activeIncidentId) return
    setDeploying(true)

    try {
      await fetch(`/approve/${activeIncidentId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true })
      })

      // Stream deployment
      const eventSource = new EventSource(`/deploy-stream/${activeIncidentId}`)
      const startTime = Date.now()

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'log') {
            setDeployLogs(prev => [...prev, data])
          }

          if (data.type === 'git_push') {
            setDeployLogs(prev => [...prev, data])
          }

          if (data.type === 'completion') {
            const elapsed = Math.round((Date.now() - startTime) / 1000)
            const mins = Math.floor(elapsed / 60)
            const secs = elapsed % 60
            setMttr(`${mins}m ${secs}s`)
            setMemAfter(data.memoryAfter ? parseInt(data.memoryAfter) : 128)
            setResolved(true)
            setDeploying(false)
            eventSource.close()
          }

          if (data.type === 'agent') {
            setDeployLogs(prev => [...prev, {
              type: 'agent',
              message: `[${data.agent}] ${data.status}`,
              timestamp: new Date().toISOString()
            }])
          }

          if (data.type === 'error') {
            setDeployLogs(prev => [...prev, { ...data, type: 'error' }])
            setDeploying(false)
            eventSource.close()
          }
        } catch (e) {
          console.error('Deploy parse error:', e)
        }
      }

      eventSource.onerror = () => {
        eventSource.close()
        setDeploying(false)
      }
    } catch (e) {
      console.error('Approve error:', e)
      setDeploying(false)
    }
  }, [activeIncidentId])

  const handleEscalate = useCallback(() => {
    if (!activeIncidentId) return
    setDeployLogs(prev => [...prev, {
      type: 'info',
      message: 'Incident escalated to senior engineer',
      timestamp: new Date().toISOString()
    }])
  }, [activeIncidentId])

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="dashboard__header">
        <div className="dashboard__header-left">
          <span className="dashboard__logo">
            <span className="dashboard__logo-ops">OPS</span>
            <span className="dashboard__logo-bob">BOB</span>
          </span>
        </div>
        <div className="dashboard__header-center">
          <span className="dashboard__header-title">PRODUCTION INTELLIGENCE PLATFORM</span>
        </div>
        <div className="dashboard__header-right">
          <div className={`dashboard__status dashboard__status--${systemStatus}`}>
            <span className="dashboard__status-dot" />
            <span>{systemStatus === 'incident' ? 'INCIDENT ACTIVE' : 'ALL SYSTEMS NOMINAL'}</span>
          </div>
          <Tag type="blue" size="sm" renderIcon={IbmCloud}>IBM</Tag>
        </div>
      </header>

      {/* Three-panel layout */}
      <main className="dashboard__main">
        {/* Left Panel — Incident Feed */}
        <section className="dashboard__panel dashboard__panel--left">
          <IncidentFeed
            incidents={incidents}
            onAnalyze={handleAnalyze}
            analyzingId={activeIncidentId}
            onOrchestrate={handleOrchestrateRun}
            orchestratingId={orchState === 'running' ? orchIncidentId : null}
          />
        </section>

        {/* Center Panel — Analysis Engine */}
        <section className="dashboard__panel dashboard__panel--center">
          <div className="dashboard__panel-header">
            {centerMode === 'orchestrate' ? <Bot size={16} /> : <Activity size={16} />}
            <span>{centerMode === 'orchestrate' ? 'ORCHESTRATE PIPELINE' : 'BOB ANALYSIS ENGINE'}</span>
            {(activeIncidentId || orchIncidentId) && (
              <Tag type="blue" size="sm">{orchIncidentId || activeIncidentId}</Tag>
            )}
            <div className="dashboard__center-tabs">
              <button
                className={`dashboard__center-tab ${centerMode === 'bob' ? 'dashboard__center-tab--active' : ''}`}
                onClick={() => setCenterMode('bob')}
              >BOB</button>
              <button
                className={`dashboard__center-tab ${centerMode === 'orchestrate' ? 'dashboard__center-tab--active' : ''}`}
                onClick={() => setCenterMode('orchestrate')}
              >ORCHESTRATE</button>
            </div>
          </div>
          <div className="dashboard__panel-content">
            {centerMode === 'orchestrate' ? (
              <OrchestratePanel
                incidentId={orchIncidentId}
                onRun={() => orchIncidentId && handleOrchestrateRun(orchIncidentId)}
                pipelineState={orchState}
                agentResults={orchAgentResults}
                commanderText={orchCommanderText}
                decision={orchDecision}
                elapsed={orchElapsed}
                progressMsg={orchProgressMsg}
              />
            ) : !activeIncidentId ? (
              <div className="dashboard__empty-state">
                <div className="dashboard__empty-icon">
                  <Lottie 
                    animationData={chatbotAnimation} 
                    loop={true}
                    style={{ width: 200, height: 200 }}
                  />
                </div>
                <span>Select an incident to begin analysis</span>
              </div>
            ) : (
              <>
                <DiagnosisCard phases={phases} currentPhase={currentPhase} analysisError={analysisError} />
                {riskAssessment && <RiskAssessmentCard assessment={riskAssessment} />}
                <OrchestrationFlowCard
                  phases={phases}
                  currentPhase={currentPhase}
                  riskAssessment={riskAssessment}
                  executionFeed={executionFeed}
                  pipelineComplete={pipelineComplete}
                  analysisError={analysisError}
                  orchestrateStatus={orchestrateStatus}
                  orchestrateDecision={orchestrateDecision}
                />
                {Object.keys(agentResults).length > 0 && (
                  <AgentPipelineStatus
                    agentResults={agentResults}
                    pipelineComplete={pipelineComplete}
                  />
                )}
              </>
            )}
          </div>
        </section>

        {/* Right Panel — Command & Control */}
        <section className="dashboard__panel dashboard__panel--right">
          <FixActions
            analysisComplete={analysisComplete}
            analysisError={analysisError}
            pipelineResults={pipelineResults}
            orchestrateDecision={orchestrateDecision}
            onApprove={handleApprove}
            onEscalate={handleEscalate}
            deploying={deploying}
          />
          <AuditTrail logs={deployLogs} />
          <MemoryTelemetry
            memBefore={memBefore}
            memAfter={memAfter}
            mttr={mttr}
            resolved={resolved}
          />
          <DemoServiceLogs />
        </section>
      </main>

      {/* System Health Bar */}
      <SystemHealthBar />
    </div>
  )
}

export default Dashboard
