import React from 'react'
import { Button, Tag } from '@carbon/react'
import { Checkmark, WarningAlt, UserAdmin, Bot } from '@carbon/icons-react'
import './FixActions.css'

function FixActions({ analysisComplete, analysisError, pipelineResults, orchestrateDecision, onApprove, onEscalate, deploying }) {
  const routing = pipelineResults?.agents?.approval_router
  const recommendation = routing?.recommendation || 'review'
  const blocked = recommendation === 'escalate' || !pipelineResults || Boolean(analysisError)

  // Orchestrate commander state
  const orcDecision = orchestrateDecision?.decision
  const orcUsed = orchestrateDecision?.orchestrate_used
  const orcPending = analysisComplete && pipelineResults && !orchestrateDecision

  if (analysisError) {
    return (
      <div className="fix-actions fix-actions--disabled">
        <div className="fix-actions__header">
          <span className="fix-actions__title">RESPONSE ACTIONS</span>
          <Tag type="red" size="sm">FAILED</Tag>
        </div>
        <p className="fix-actions__waiting">Analysis failed: {analysisError}</p>
        <div className="fix-actions__buttons">
          <Button
            kind="danger--tertiary"
            size="md"
            className="fix-actions__escalate"
            onClick={onEscalate}
            disabled={deploying}
            renderIcon={WarningAlt}
          >
            ESCALATE TO HUMAN
          </Button>
        </div>
      </div>
    )
  }

  if (!analysisComplete) {
    return (
      <div className="fix-actions fix-actions--disabled">
        <div className="fix-actions__header">
          <span className="fix-actions__title">RESPONSE ACTIONS</span>
        </div>
        <p className="fix-actions__waiting">Waiting for Bob's analysis to complete...</p>
      </div>
    )
  }

  return (
    <div className="fix-actions">
      <div className="fix-actions__header">
        <span className="fix-actions__title">RESPONSE ACTIONS</span>
        {routing && (
          <Tag type={recommendation === 'approve' ? 'green' : recommendation === 'escalate' ? 'red' : 'warm-gray'} size="sm">
            {recommendation.toUpperCase()}
          </Tag>
        )}
      </div>

      {routing?.routing_reason && (
        <p className="fix-actions__reason">
          {routing.routing_reason}
        </p>
      )}

      {/* Orchestrate commander status */}
      {orcPending && (
        <p className="fix-actions__reason fix-actions__reason--orch">
          <Bot size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          Orchestrate Commander evaluating…
        </p>
      )}
      {orchestrateDecision && (
        <div className="fix-actions__orch-banner">
          <Bot size={14} />
          <span>
            Orchestrate Commander:{' '}
            <strong>{orcDecision?.toUpperCase()}</strong>
            {!orcUsed && orchestrateDecision.error && (
              <span style={{ opacity: 0.6 }}> (fallback — {orchestrateDecision.error})</span>
            )}
          </span>
        </div>
      )}

      <div className="fix-actions__buttons">
        {/* Hide manual approve if Orchestrate already auto-deploying */}
        {!blocked && orcDecision !== 'approve' && (
          <Button
            kind="primary"
            size="md"
            className="fix-actions__approve"
            onClick={onApprove}
            disabled={deploying}
            renderIcon={Checkmark}
          >
            {deploying ? 'DEPLOYING...' : 'APPROVE & DEPLOY FIX'}
          </Button>
        )}
        {orcDecision === 'approve' && (
          <p className="fix-actions__reason" style={{ color: 'var(--cds-support-success, #42be65)' }}>
            <Checkmark size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
            {deploying ? 'Auto-deploying to production…' : 'Deployed by Orchestrate Commander'}
          </p>
        )}
        <Button
          kind="danger--tertiary"
          size="md"
          className="fix-actions__escalate"
          onClick={onEscalate}
          disabled={deploying}
          renderIcon={blocked ? WarningAlt : UserAdmin}
        >
          {blocked ? 'ESCALATE (DEPLOY BLOCKED)' : 'ESCALATE TO HUMAN'}
        </Button>
      </div>
    </div>
  )
}

export default FixActions
