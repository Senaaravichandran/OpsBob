import React from 'react'
import { Tag, InlineLoading } from '@carbon/react'
import { Checkmark, WarningAlt, Close, Search, Chemistry, DecisionTree, DocumentTasks } from '@carbon/icons-react'
import './AgentPipelineStatus.css'

const AGENTS = [
  { id: 'static_analysis', label: 'Static Analysis', IconComponent: Search },
  { id: 'test_runner', label: 'Test Runner', IconComponent: Chemistry },
  { id: 'approval_router', label: 'Approval Router', IconComponent: DecisionTree },
  { id: 'post_incident', label: 'Post-Incident', IconComponent: DocumentTasks }
]

function AgentPipelineStatus({ agentResults, pipelineComplete }) {
  const getAgentStatus = (agentId) => {
    if (!agentResults) return 'pending'
    const result = agentResults[agentId]
    if (!result) return 'pending'
    if (result.status === 'running') return 'running'
    const verdict = result.verdict || result.recommendation || result.status
    if (verdict === 'PASS' || verdict === 'approve' || verdict === 'complete') return 'pass'
    if (verdict === 'WARN' || verdict === 'review') return 'warn'
    if (verdict === 'FAIL' || verdict === 'escalate') return 'fail'
    return 'complete'
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pass': case 'complete': return <Checkmark size={14} />
      case 'warn': return <WarningAlt size={14} />
      case 'fail': return <Close size={14} />
      case 'running': return <InlineLoading description="" />
      default: return <span className="agent-dot agent-dot--pending" />
    }
  }

  return (
    <div className="agent-pipeline">
      <div className="agent-pipeline__header">
        <span className="agent-pipeline__title">VERIFICATION PIPELINE</span>
        {pipelineComplete && (
          <Tag type="green" size="sm">COMPLETE</Tag>
        )}
      </div>
      <div className="agent-pipeline__steps">
        {AGENTS.map((agent, i) => {
          const status = getAgentStatus(agent.id)
          const result = agentResults?.[agent.id]
          const IconComponent = agent.IconComponent
          return (
            <div key={agent.id} className={`agent-step agent-step--${status}`}>
              <div className="agent-step__connector">
                {i > 0 && <div className={`agent-step__line agent-step__line--${status}`} />}
              </div>
              <div className="agent-step__indicator">
                {getStatusIcon(status)}
              </div>
              <div className="agent-step__content">
                <div className="agent-step__header">
                  <span className="agent-step__icon">
                    <IconComponent size={16} />
                  </span>
                  <span className="agent-step__label">{agent.label}</span>
                  <Tag type={
                    status === 'pass' || status === 'complete' ? 'green' :
                    status === 'warn' ? 'warm-gray' :
                    status === 'fail' ? 'red' :
                    status === 'running' ? 'blue' : 'cool-gray'
                  } size="sm">
                    {(result?.verdict || result?.recommendation || status).toUpperCase()}
                  </Tag>
                </div>
                {result?.duration_ms && (
                  <span className="agent-step__duration">{result.duration_ms}ms</span>
                )}
                {result?.findings?.length > 0 && (
                  <div className="agent-step__findings">
                    {result.findings.slice(0, 2).map((f, i) => (
                      <span key={i} className="agent-step__finding">• {f}</span>
                    ))}
                  </div>
                )}
                {result?.routing_reason && (
                  <span className="agent-step__reason">{result.routing_reason}</span>
                )}
                {result?.fallback && (
                  <Tag type="warm-gray" size="sm" className="agent-step__fallback">FALLBACK</Tag>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default AgentPipelineStatus
