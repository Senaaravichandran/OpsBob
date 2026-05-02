import React from 'react'
import { Tag } from '@carbon/react'
import { Checkmark } from '@carbon/icons-react'
import './MemoryTelemetry.css'

function MemoryTelemetry({ memBefore, memAfter, mttr, resolved }) {
  return (
    <div className="telemetry">
      <div className="telemetry__header">
        <span className="telemetry__title">MEMORY TELEMETRY</span>
      </div>
      <div className="telemetry__grid">
        <div className="telemetry__item">
          <span className="telemetry__label">BEFORE</span>
          <span className="telemetry__value telemetry__value--red">
            {memBefore || '—'} MB
          </span>
          <Tag type="red" size="sm">DEGRADED</Tag>
        </div>
        <div className="telemetry__item">
          <span className="telemetry__label">AFTER</span>
          <span className={`telemetry__value ${resolved ? 'telemetry__value--green' : ''}`}>
            {memAfter || '—'} MB
          </span>
          {resolved && <Tag type="green" size="sm">NOMINAL</Tag>}
        </div>
      </div>
      {mttr && (
        <div className="telemetry__mttr">
          <span className="telemetry__mttr-label">MEAN TIME TO RESOLUTION</span>
          <span className="telemetry__mttr-value">{mttr}</span>
          {resolved && (
            <div className="telemetry__resolved-banner">
              <Checkmark size={16} style={{ marginRight: '6px' }} />
              INCIDENT RESOLVED BY IBM BOB
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default MemoryTelemetry
