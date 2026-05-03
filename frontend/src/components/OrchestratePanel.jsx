import React from 'react'
import { Button, Tag, InlineLoading } from '@carbon/react'
import {
  Renew, Bot, Search, Chemistry, DecisionTree, DocumentTasks, WarningAlt
} from '@carbon/icons-react'
import './OrchestratePanel.css'

// ── Per-agent result renderers ──────────────────────────────────

function VerdictTag({ verdict }) {
  if (!verdict) return null
  const v = String(verdict).toLowerCase()
  const type =
    v === 'pass'    || v === 'approve'  ? 'green'     :
    v === 'warn'    || v === 'review'   ? 'warm-gray' :
    v === 'fail'    || v === 'escalate' ? 'red'       : 'cool-gray'
  return <Tag type={type} size="sm">{String(verdict).toUpperCase()}</Tag>
}

function StaticAnalysisResult({ result }) {
  return (
    <div className="orc-result">
      {result.findings?.length > 0 && (
        <ul className="orc-findings">
          {result.findings.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      )}
      {result.risk_areas?.length > 0 && (
        <div className="orc-tags">
          {result.risk_areas.map((r, i) => (
            <Tag key={i} type="warm-gray" size="sm">{r}</Tag>
          ))}
        </div>
      )}
    </div>
  )
}

function TestRunnerResult({ result }) {
  return (
    <div className="orc-result">
      <div className="orc-test-stats">
        <span className="orc-stat orc-stat--pass">✓ {result.passed ?? 0} passed</span>
        <span className="orc-stat orc-stat--fail">✗ {result.failed ?? 0} failed</span>
        <span className="orc-stat orc-stat--skip">⊘ {result.skipped ?? 0} skipped</span>
      </div>
      {result.output && (
        <pre className="orc-output">{result.output}</pre>
      )}
      {result.fallback && (
        <Tag type="warm-gray" size="sm">FALLBACK MODE</Tag>
      )}
    </div>
  )
}

function ApprovalResult({ result }) {
  const sigs = result.signals || {}
  return (
    <div className="orc-result">
      {result.routing_reason && (
        <p className="orc-reason">{result.routing_reason}</p>
      )}
      {Object.keys(sigs).length > 0 && (
        <div className="orc-signals">
          {Object.entries(sigs).map(([k, v]) => (
            <div key={k} className="orc-signal">
              <span className="orc-signal__key">{k.replace(/_/g, ' ')}</span>
              <span className="orc-signal__val">{String(v).toUpperCase()}</span>
            </div>
          ))}
        </div>
      )}
      {result.route_to && (
        <p className="orc-route">Route to: <strong>{result.route_to}</strong></p>
      )}
      {result.urgency && (
        <Tag type={result.urgency === 'high' ? 'red' : 'warm-gray'} size="sm">
          URGENCY: {result.urgency.toUpperCase()}
        </Tag>
      )}
    </div>
  )
}

function PostIncidentResult({ result }) {
  const report = result.report || {}
  return (
    <div className="orc-result">
      {report.root_cause && (
        <div className="orc-report-row">
          <span className="orc-report-key">Root Cause</span>
          <span>{report.root_cause}</span>
        </div>
      )}
      {report.fix_summary && (
        <div className="orc-report-row">
          <span className="orc-report-key">Fix</span>
          <span>{report.fix_summary}</span>
        </div>
      )}
      {report.prevention && (
        <div className="orc-report-row">
          <span className="orc-report-key">Prevention</span>
          <span>{report.prevention}</span>
        </div>
      )}
      {result.runbook_entry && (
        <pre className="orc-runbook">{result.runbook_entry}</pre>
      )}
    </div>
  )
}

// ── Agent card ──────────────────────────────────────────────────

const AGENTS = [
  { id: 'static_analysis',  label: 'Static Analysis',     Icon: Search },
  { id: 'test_runner',      label: 'Test Runner',          Icon: Chemistry },
  { id: 'approval_router',  label: 'Approval Router',      Icon: DecisionTree },
  { id: 'post_incident',    label: 'Post-Incident Report', Icon: DocumentTasks },
]

function AgentCard({ agent, result, isRunning }) {
  const { id, label, Icon } = agent
  const verdict = result?.verdict || result?.recommendation
  const hasResult = Boolean(result)

  const borderClass = !hasResult
    ? 'orc-card--pending'
    : isRunning
    ? 'orc-card--running'
    : verdict === 'PASS'    || verdict === 'approve'  ? 'orc-card--pass'
    : verdict === 'WARN'    || verdict === 'review'   ? 'orc-card--warn'
    : verdict === 'FAIL'    || verdict === 'escalate' ? 'orc-card--fail'
    : 'orc-card--done'

  return (
    <div className={`orc-card ${borderClass}`}>
      <div className="orc-card__header">
        <Icon size={16} className="orc-card__icon" />
        <span className="orc-card__label">{label}</span>
        {isRunning && !hasResult && <InlineLoading />}
        {hasResult && <VerdictTag verdict={verdict} />}
        {result?.duration_ms !== undefined && (
          <span className="orc-card__ms">{result.duration_ms}ms</span>
        )}
      </div>
      {result && id === 'static_analysis' && <StaticAnalysisResult result={result} />}
      {result && id === 'test_runner'     && <TestRunnerResult     result={result} />}
      {result && id === 'approval_router' && <ApprovalResult       result={result} />}
      {result && id === 'post_incident'   && <PostIncidentResult   result={result} />}
    </div>
  )
}

// ── Main panel ──────────────────────────────────────────────────

export default function OrchestratePanel({
  incidentId,
  onRun,
  pipelineState,
  agentResults,
  commanderText,
  decision,
  elapsed,
  progressMsg,
}) {
  const isRunning  = pipelineState === 'running'
  const isComplete = pipelineState === 'complete'
  const isError    = pipelineState === 'error'

  if (!incidentId) {
    return (
      <div className="orc-panel orc-panel--empty">
        <Bot size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
        <p>Select an incident from the feed, then click <strong>ORCHESTRATE</strong> to trigger the IBM watsonx 4-agent pipeline.</p>
      </div>
    )
  }

  const decisionType =
    decision === 'approve'  ? 'green'     :
    decision === 'escalate' ? 'red'       :
    decision === 'reject'   ? 'red'       : 'warm-gray'

  return (
    <div className="orc-panel">
      {/* Header */}
      <div className="orc-panel__header">
        <div className="orc-panel__title-row">
          <Bot size={18} className="orc-panel__bot-icon" />
          <span className="orc-panel__title">IBM watsonx ORCHESTRATE PIPELINE</span>
          <Tag type="blue" size="sm">{incidentId}</Tag>
          {isComplete && decision && (
            <Tag type={decisionType} size="sm">
              {decision.toUpperCase()}
            </Tag>
          )}
        </div>
        <Button
          kind={isComplete ? 'ghost' : 'primary'}
          size="sm"
          renderIcon={Renew}
          onClick={onRun}
          disabled={isRunning}
        >
          {isRunning ? 'RUNNING…' : isComplete ? 'RE-RUN' : 'RUN PIPELINE'}
        </Button>
      </div>

      {/* Progress bar while running */}
      {isRunning && (
        <div className="orc-progress">
          <InlineLoading description={progressMsg || `Running… (${elapsed}s)`} />
          <div className="orc-progress-bar">
            <div
              className="orc-progress-fill"
              style={{ width: `${Math.min((elapsed / 90) * 100, 95)}%` }}
            />
          </div>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="orc-error">
          <WarningAlt size={16} />
          <span>Pipeline error — check backend logs or retry</span>
        </div>
      )}

      {/* 4 Agent cards */}
      <div className="orc-agents">
        {AGENTS.map(agent => (
          <AgentCard
            key={agent.id}
            agent={agent}
            result={agentResults[agent.id]}
            isRunning={isRunning}
          />
        ))}
      </div>

      {/* Commander summary */}
      {commanderText && (
        <div className="orc-commander">
          <div className="orc-commander__header">
            <Bot size={14} />
            <span>COMMANDER SUMMARY</span>
            {decision && <VerdictTag verdict={decision} />}
          </div>
          <p className="orc-commander__text">{commanderText}</p>
        </div>
      )}
    </div>
  )
}
