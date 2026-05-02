import React from 'react'
import { Tag, InlineLoading } from '@carbon/react'
import './DiagnosisCard.css'

const PHASE_CONFIG = {
  ask: { label: 'ASK — CODE READING', color: 'var(--ob-accent-blue)', tagType: 'blue' },
  plan: { label: 'PLAN — ROOT CAUSE', color: 'var(--ob-accent-amber)', tagType: 'warm-gray' },
  code: { label: 'CODE — FIX GENERATION', color: 'var(--ob-accent-green)', tagType: 'green' }
}

function DiagnosisCard({ phases, currentPhase, analysisError }) {
  const firstIncompletePhase = ['ask', 'plan', 'code'].find(phase => !(phases?.[phase]?.length > 0))

  return (
    <div className="diagnosis">
      {analysisError && (
        <div className="diagnosis__phase diagnosis__phase--error">
          <div className="diagnosis__phase-header">
            <span className="diagnosis__phase-label">ANALYSIS ERROR</span>
            <div className="diagnosis__phase-status">
              <Tag type="red" size="sm">FAILED</Tag>
            </div>
          </div>
          <div className="diagnosis__phase-content">
            <pre className="diagnosis__text">{analysisError}</pre>
          </div>
        </div>
      )}
      {['ask', 'plan', 'code'].map(phase => {
        const config = PHASE_CONFIG[phase]
        const content = phases?.[phase]
        const isActive = currentPhase === phase
        const isDone = content && content.length > 0
        const isFailed = Boolean(analysisError) && firstIncompletePhase === phase
        const status = isDone ? 'COMPLETE' : isFailed ? 'FAILED' : isActive ? 'PROCESSING' : 'PENDING'

        return (
          <div key={phase}
            className={`diagnosis__phase diagnosis__phase--${phase} ${isDone ? 'diagnosis__phase--done' : ''} ${isActive ? 'diagnosis__phase--active' : ''} ${isFailed ? 'diagnosis__phase--error' : ''}`}
            style={{ '--phase-color': config.color }}
          >
            <div className="diagnosis__phase-header">
              <span className="diagnosis__phase-label">{config.label}</span>
              <div className="diagnosis__phase-status">
                {isActive && <InlineLoading description="" className="diagnosis__loading" />}
                <Tag type={isDone ? config.tagType : isFailed ? 'red' : 'cool-gray'} size="sm">{status}</Tag>
              </div>
            </div>
            <div className="diagnosis__phase-content">
              {content ? (
                <pre className="diagnosis__text">{content}</pre>
              ) : (
                <span className="diagnosis__placeholder">
                  {isFailed ? 'Analysis stopped due to an upstream error.' : isActive ? 'Bob is analyzing...' : 'Waiting...'}
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
