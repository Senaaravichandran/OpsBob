import React from 'react'
import { Tag, InlineLoading } from '@carbon/react'
import './DiagnosisCard.css'

const PHASE_CONFIG = {
  ask: { label: 'ASK — CODE READING', color: 'var(--ob-accent-blue)', tagType: 'blue' },
  plan: { label: 'PLAN — ROOT CAUSE', color: 'var(--ob-accent-amber)', tagType: 'warm-gray' },
  code: { label: 'CODE — FIX GENERATION', color: 'var(--ob-accent-green)', tagType: 'green' }
}

function DiagnosisCard({ phases, currentPhase }) {
  return (
    <div className="diagnosis">
      {['ask', 'plan', 'code'].map(phase => {
        const config = PHASE_CONFIG[phase]
        const content = phases?.[phase]
        const isActive = currentPhase === phase
        const isDone = content && content.length > 0
        const status = isDone ? 'COMPLETE' : isActive ? 'PROCESSING' : 'PENDING'

        return (
          <div key={phase}
            className={`diagnosis__phase diagnosis__phase--${phase} ${isDone ? 'diagnosis__phase--done' : ''} ${isActive ? 'diagnosis__phase--active' : ''}`}
            style={{ '--phase-color': config.color }}
          >
            <div className="diagnosis__phase-header">
              <span className="diagnosis__phase-label">{config.label}</span>
              <div className="diagnosis__phase-status">
                {isActive && <InlineLoading description="" className="diagnosis__loading" />}
                <Tag type={isDone ? config.tagType : 'cool-gray'} size="sm">{status}</Tag>
              </div>
            </div>
            <div className="diagnosis__phase-content">
              {content ? (
                <pre className="diagnosis__text">{content}</pre>
              ) : (
                <span className="diagnosis__placeholder">
                  {isActive ? 'Bob is analyzing...' : 'Waiting...'}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default DiagnosisCard
