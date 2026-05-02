import React from 'react'
import { InlineLoading, Tag } from '@carbon/react'
import './OrchestrationFlowCard.css'

const STAGES = [
  { id: 'brainstorm', label: 'BRAINSTORM', description: 'Context assembly and code reading' },
  { id: 'plan', label: 'PLAN', description: 'Root cause and risk framing' },
  { id: 'execute', label: 'EXECUTE', description: 'Fix generation, verification, and commander decision' }
]

function normalizeStatus(status) {
  const value = String(status || 'queued').toLowerCase()

  if (['running', 'processing', 'in_progress'].includes(value)) return 'running'
  if (['pass', 'complete', 'approve', 'approved', 'success'].includes(value)) return 'complete'
  if (['warn', 'review'].includes(value)) return 'review'
  if (['fail', 'failed', 'error', 'reject', 'escalate', 'blocked'].includes(value)) return 'failed'
  if (['queued', 'pending'].includes(value)) return 'queued'

  return value
}

function getTagType(status) {
  switch (normalizeStatus(status)) {
    case 'running':
      return 'blue'
    case 'complete':
      return 'green'
    case 'review':
      return 'warm-gray'
    case 'failed':
      return 'red'
    default:
      return 'cool-gray'
  }
}

function formatStatusLabel(status) {
  return String(status || 'queued').replace(/_/g, ' ').toUpperCase()
}

function truncate(text, maxLength = 360) {
  if (!text) return ''
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text
}

function getOverallStatus({ currentPhase, executionFeed, orchestrateDecision, orchestrateStatus, analysisError }) {
  if (analysisError) return 'failed'
  if (orchestrateDecision?.done) return orchestrateDecision.decision || 'complete'
  if (normalizeStatus(orchestrateStatus) === 'running') return 'running'
  if (currentPhase || executionFeed.length > 0) return 'running'
  return 'queued'
}

function getStageStatus(stageId, { phases, currentPhase, executionFeed, pipelineComplete, analysisError, orchestrateStatus, orchestrateDecision }) {
  if (stageId === 'brainstorm') {
    if (currentPhase === 'ask') return 'running'
    if (phases?.ask) return 'complete'
    if (analysisError) return 'failed'
    return 'queued'
  }

  if (stageId === 'plan') {
    if (currentPhase === 'plan') return 'running'
    if (phases?.plan) return 'complete'
    if (analysisError && (currentPhase || phases?.ask)) return 'failed'
    return 'queued'
  }

  const hasExecutionOutput = Boolean(phases?.code || executionFeed.length > 0 || orchestrateDecision)
  const hasRunningExecution = currentPhase === 'code'
    || normalizeStatus(orchestrateStatus) === 'running'
    || executionFeed.some((entry) => normalizeStatus(entry.status) === 'running')

  if (hasRunningExecution) return 'running'
  if (orchestrateDecision?.done) return 'complete'
  if (hasExecutionOutput && !pipelineComplete) return 'running'
  if (pipelineComplete || hasExecutionOutput) return 'complete'
  if (analysisError && (phases?.plan || phases?.ask)) return 'failed'
  return 'queued'
}

function OrchestrationFlowCard({
  phases,
  currentPhase,
  riskAssessment,
  executionFeed,
  pipelineComplete,
  analysisError,
  orchestrateStatus,
  orchestrateDecision
}) {
  const overallStatus = getOverallStatus({ currentPhase, executionFeed, orchestrateDecision, orchestrateStatus, analysisError })
  const recentExecutionFeed = executionFeed.slice(-6)

  return (
    <div className="orchestration-flow">
      <div className="orchestration-flow__header">
        <div>
          <span className="orchestration-flow__title">LIVE ORCHESTRATION</span>
          <p className="orchestration-flow__subtitle">Live agent outputs across the incident workflow</p>
        </div>
        <Tag type={getTagType(overallStatus)} size="sm">{formatStatusLabel(overallStatus)}</Tag>
      </div>

      <div className="orchestration-flow__stages">
        {STAGES.map((stage) => {
          const status = getStageStatus(stage.id, {
            phases,
            currentPhase,
            executionFeed,
            pipelineComplete,
            analysisError,
            orchestrateStatus,
            orchestrateDecision
          })

          return (
            <section key={stage.id} className={`orchestration-stage orchestration-stage--${status}`}>
              <div className="orchestration-stage__header">
                <div>
                  <span className="orchestration-stage__label">{stage.label}</span>
                  <p className="orchestration-stage__description">{stage.description}</p>
                </div>
                <div className="orchestration-stage__status">
                  {normalizeStatus(status) === 'running' && <InlineLoading description="" className="orchestration-stage__loading" />}
                  <Tag type={getTagType(status)} size="sm">{formatStatusLabel(status)}</Tag>
                </div>
              </div>

              {stage.id === 'brainstorm' && (
                <div className="orchestration-stage__body">
                  {phases?.ask ? (
                    <pre className="orchestration-stage__text">{truncate(phases.ask)}</pre>
                  ) : (
                    <span className="orchestration-stage__placeholder">
                      {analysisError ? 'Brainstorming stopped because analysis failed.' : currentPhase === 'ask' ? 'Bob is assembling context and reading the codebase...' : 'Waiting for incident analysis to start.'}
                    </span>
                  )}
                </div>
              )}

              {stage.id === 'plan' && (
                <div className="orchestration-stage__body">
                  {phases?.plan ? (
                    <pre className="orchestration-stage__text">{truncate(phases.plan)}</pre>
                  ) : (
                    <span className="orchestration-stage__placeholder">
                      {analysisError ? 'Planning stopped because analysis failed.' : currentPhase === 'plan' ? 'Bob is forming the root-cause plan...' : 'Waiting for brainstorm output.'}
                    </span>
                  )}
                  {riskAssessment && (
                    <div className="orchestration-stage__meta">
                      {riskAssessment.confidence && (
                        <Tag type="warm-gray" size="sm">CONFIDENCE {String(riskAssessment.confidence).toUpperCase()}</Tag>
                      )}
                      {riskAssessment.blast_radius && (
                        <Tag type="cool-gray" size="sm">BLAST {riskAssessment.blast_radius}</Tag>
                      )}
                    </div>
                  )}
                </div>
              )}

              {stage.id === 'execute' && (
                <div className="orchestration-stage__body orchestration-stage__body--execute">
                  {phases?.code ? (
                    <pre className="orchestration-stage__text orchestration-stage__text--code">{truncate(phases.code, 420)}</pre>
                  ) : (
                    <span className="orchestration-stage__placeholder">
                      {analysisError ? 'Execution did not start because analysis failed.' : currentPhase === 'code' ? 'Bob is generating the candidate fix...' : 'Waiting for plan approval inputs.'}
                    </span>
                  )}

                  {recentExecutionFeed.length > 0 && (
                    <div className="orchestration-stage__events">
                      {recentExecutionFeed.map((entry) => (
                        <div key={entry.id} className={`orchestration-event orchestration-event--${normalizeStatus(entry.status)}`}>
                          <div className="orchestration-event__header">
                            <span className="orchestration-event__actor">{entry.actor}</span>
                            <Tag type={getTagType(entry.status)} size="sm">{formatStatusLabel(entry.status)}</Tag>
                          </div>
                          <span className="orchestration-event__message">{entry.message}</span>
                          {entry.detail && entry.detail !== entry.message && (
                            <pre className="orchestration-event__detail">{truncate(entry.detail, 220)}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}

export default OrchestrationFlowCard