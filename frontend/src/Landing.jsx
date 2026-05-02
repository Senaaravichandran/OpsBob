import React from 'react'
import { Button, Tag } from '@carbon/react'
import { Launch } from '@carbon/icons-react'
import './Landing.css'

function Landing({ onEnter, transitioning }) {
  return (
    <div className={`landing ${transitioning ? 'landing--fade-out' : ''}`}>
      {/* Subtle grid background */}
      <div className="landing__grid-bg" />
      
      {/* Scanline effect */}
      <div className="landing__scanline" />

      <div className="landing__content">
        {/* Logo */}
        <div className="landing__logo-container">
          <div className="landing__logo-glow" />
          <h1 className="landing__logo">
            <span className="landing__logo-ops">OPS</span>
            <span className="landing__logo-bob">BOB</span>
          </h1>
        </div>

        {/* Tagline */}
        <p className="landing__tagline">
          AUTONOMOUS PRODUCTION INTELLIGENCE PLATFORM
        </p>

        {/* Status indicator */}
        <div className="landing__status">
          <span className="landing__status-dot" />
          <Tag type="green" size="sm">SYSTEM ONLINE</Tag>
        </div>

        {/* IBM Badge */}
        <p className="landing__ibm-badge">
          POWERED BY IBM BOB ORCHESTRATOR
        </p>

        {/* Enter button */}
        <Button
          kind="primary"
          size="lg"
          renderIcon={Launch}
          className="landing__enter-btn"
          onClick={onEnter}
        >
          ENTER COMMAND CENTER
        </Button>

        {/* Tech stack */}
        <div className="landing__tech-stack">
          {['Bob', 'watsonx.ai', 'Orchestrate', 'Instana', 'Carbon', 'Code Engine'].map(t => (
            <Tag key={t} type="cool-gray" size="sm" className="landing__tech-tag">{t}</Tag>
          ))}
        </div>
      </div>

      <div className="landing__footer">
        <span>TEAM DRAGORITHM</span>
        <span>IBM BOB HACKATHON 2026</span>
      </div>
    </div>
  )
}

export default Landing
