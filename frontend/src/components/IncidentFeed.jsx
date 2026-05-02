import React from 'react'
import { Tag, Button } from '@carbon/react'
import { Warning, Renew } from '@carbon/icons-react'
import './IncidentFeed.css'

function IncidentFeed({ incidents, onAnalyze, analyzingId }) {
  const incidentList = Object.entries(incidents || {}).map(([id, data]) => ({
    id,
    ...data
  }))

  if (incidentList.length === 0) {
    return (
      <div className="incident-feed">
        <div className="incident-feed__header">
          <span className="incident-feed__title">INCIDENT FEED</span>
          <span className="incident-feed__count">0</span>
        </div>
        <div className="incident-feed__empty">
          <div className="incident-feed__empty-dot" />
          <span>MONITORING ACTIVE</span>
          <span className="incident-feed__empty-sub">Waiting for incidents...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="incident-feed">
      <div className="incident-feed__header">
        <span className="incident-feed__title">INCIDENT FEED</span>
        <span className="incident-feed__count">{incidentList.length}</span>
      </div>
      <div className="incident-feed__list">
        {incidentList.map(inc => (
          <div key={inc.id} className={`incident-card incident-card--${inc.status}`}>
            <div className="incident-card__header">
              <Warning size={16} className="incident-card__icon" />
              <span className="incident-card__id">{inc.incident_id || inc.id}</span>
              <Tag type={inc.severity === 'HIGH' || inc.severity >= 8 ? 'red' : 'warm-gray'} size="sm">
                {typeof inc.severity === 'number' ? `SEV-${inc.severity}` : inc.severity}
              </Tag>
            </div>
            <div className="incident-card__service">{inc.service || inc.entityName || 'unknown'}</div>
            <div className="incident-card__type">{inc.type || 'MEMORY_LEAK'}</div>
            <div className="incident-card__meta">
              <span>{inc.received_at ? new Date(inc.received_at).toLocaleTimeString() : ''}</span>
              <Tag type={
                inc.status === 'resolved' ? 'green' :
                inc.status === 'analyzing' ? 'blue' :
                inc.status === 'deploying' ? 'purple' :
                'warm-gray'
              } size="sm">{(inc.status || 'received').toUpperCase()}</Tag>
            </div>
            {inc.status === 'received' && (
              <Button
                kind="danger--tertiary"
                size="sm"
                className="incident-card__analyze-btn"
                onClick={() => onAnalyze(inc.id || inc.incident_id)}
                disabled={!!analyzingId}
                renderIcon={Renew}
              >
                ANALYZE WITH BOB
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default IncidentFeed
