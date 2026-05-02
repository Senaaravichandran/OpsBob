import React from 'react'
import { Button, Tag } from '@carbon/react'
import { Checkmark, WarningAlt, UserAdmin } from '@carbon/icons-react'
import './FixActions.css'

function FixActions({ analysisComplete, pipelineResults, onApprove, onEscalate, deploying }) {
  const routing = pipelineResults?.agents?.approval_router
  const recommendation = routing?.recommendation || 'review'
  const blocked = recommendation === 'escalate'

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

      <div className="fix-actions__buttons">
        {!blocked && (
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
