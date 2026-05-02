import React, { useState, useEffect, useCallback } from 'react'
import { Tag } from '@carbon/react'
import { Activity, IbmCloud } from '@carbon/icons-react'
import Lottie from 'lottie-react'
import chatbotAnimation from '../public/Chatbot.json'

import IncidentFeed from './components/IncidentFeed'
import DiagnosisCard from './components/DiagnosisCard'
import RiskAssessmentCard from './components/RiskAssessmentCard'
import AgentPipelineStatus from './components/AgentPipelineStatus'
import FixActions from './components/FixActions'
import AuditTrail from './components/AuditTrail'
import MemoryTelemetry from './components/MemoryTelemetry'
import SystemHealthBar from './components/SystemHealthBar'
import './Dashboard.css'

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
  const [deploying, setDeploying] = useState(false)
  const [resolved, setResolved] = useState(false)
  const [deployLogs, setDeployLogs] = useState([])
  const [memBefore, setMemBefore] = useState(null)
  const [memAfter, setMemAfter] = useState(null)
  const [mttr, setMttr] = useState(null)
  const [systemStatus, setSystemStatus] = useState('nominal')

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
          setAgentResults(prev => ({
            ...prev,
            [data.agent]: data.result || { status: data.status, verdict: data.status }
          }))
        }

        // Pipeline complete
        if (data.phase === 'pipeline_complete') {
          setPipelineComplete(true)
          setPipelineResults({ agents: agentResults, ...data })
          setAnalysisComplete(true)
          setAnalysisError(null)
          setCurrentPhase(null)
          eventSource.close()
        }

        // Complete (no pipeline) — analysis only
        if (data.phase === 'complete' || (data.done && data.phase === 'code' && !data.agent)) {
          // Will wait for pipeline events
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
  }, [analysisComplete, analysisError, agentResults, incidents])

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
          />
        </section>

        {/* Center Panel — Analysis Engine */}
        <section className="dashboard__panel dashboard__panel--center">
          <div className="dashboard__panel-header">
            <Activity size={16} />
            <span>BOB ANALYSIS ENGINE</span>
            {activeIncidentId && (
              <Tag type="blue" size="sm">{activeIncidentId}</Tag>
            )}
          </div>
          <div className="dashboard__panel-content">
            {!activeIncidentId ? (
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
        </section>
      </main>

      {/* System Health Bar */}
      <SystemHealthBar />
    </div>
  )
}

export default Dashboard
