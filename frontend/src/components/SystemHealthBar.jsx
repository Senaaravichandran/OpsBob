import React, { useState, useEffect } from 'react'
import { Tag } from '@carbon/react'
import './SystemHealthBar.css'

function SystemHealthBar() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch('/system-health')
        if (res.ok) setHealth(await res.json())
      } catch { /* silent */ }
    }
    fetchHealth()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const services = [
    { key: 'bob_shell', label: 'BOB SHELL' },
    { key: 'watsonx_ai', label: 'WATSONX.AI' },
    { key: 'orchestrate', label: 'ORCHESTRATE' },
    { key: 'instana', label: 'INSTANA' },
    { key: 'demo_service', label: 'DEMO SVC' }
  ]

  return (
    <div className="health-bar">
      {services.map(svc => {
        const status = health?.services?.[svc.key]?.status || 'unknown'
        return (
          <div key={svc.key} className="health-bar__item">
            <span className={`health-bar__dot health-bar__dot--${status}`} />
            <span className="health-bar__label">{svc.label}</span>
          </div>
        )
      })}
      <div className="health-bar__overall">
        <Tag type={health?.overall === 'nominal' ? 'green' : health?.overall === 'degraded' ? 'red' : 'warm-gray'} size="sm">
          {(health?.overall || 'CHECKING').toUpperCase()}
        </Tag>
      </div>
    </div>
  )
}

export default SystemHealthBar
