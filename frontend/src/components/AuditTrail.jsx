import React, { useRef, useEffect } from 'react'
import './AuditTrail.css'

function AuditTrail({ logs }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="audit-trail">
      <div className="audit-trail__header">
        <span className="audit-trail__title">BOBSHELL AUDIT TRAIL</span>
        <span className="audit-trail__count">{logs?.length || 0}</span>
      </div>
      <div className="audit-trail__log">
        {(!logs || logs.length === 0) ? (
          <span className="audit-trail__empty">No deployment logs yet</span>
        ) : (
          logs.map((log, i) => (
            <div key={i} className={`audit-trail__entry audit-trail__entry--${log.type || 'info'}`}>
              <span className="audit-trail__time">
                {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}
              </span>
              <span className="audit-trail__msg">{log.type === 'git_push' ? `⬆ ${log.message}` : log.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

export default AuditTrail
