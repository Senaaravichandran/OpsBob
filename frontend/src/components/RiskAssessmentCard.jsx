import React from 'react'
import { Tag } from '@carbon/react'
import { Flash } from '@carbon/icons-react'
import './RiskAssessmentCard.css'

function RiskAssessmentCard({ assessment }) {
  if (!assessment || Object.keys(assessment).length === 0) return null

  const confidence = assessment.confidence || 'medium'
  const risk = assessment.risk_level || 'medium'
  const recommendation = assessment.recommendation || 'Review carefully'
  const blastRadius = assessment.blast_radius || 'Single service'

  const getColor = (level) => {
    switch (level) {
      case 'high': return 'red'
      case 'medium': return 'warm-gray'
      case 'low': return 'green'
      default: return 'cool-gray'
    }
  }

  return (
    <div className="risk-card">
      <div className="risk-card__header">
        <span className="risk-card__title">
          <Flash size={16} style={{ marginRight: '8px' }} />
          RISK ASSESSMENT
        </span>
        <Tag type="purple" size="sm">watsonx.ai</Tag>
      </div>
      <div className="risk-card__grid">
        <div className="risk-card__item">
          <span className="risk-card__label">CONFIDENCE</span>
          <Tag type={getColor(confidence)} size="sm">{confidence.toUpperCase()}</Tag>
        </div>
        <div className="risk-card__item">
          <span className="risk-card__label">RISK LEVEL</span>
          <Tag type={getColor(risk === 'low' ? 'low' : risk === 'high' ? 'high' : 'medium')} size="sm">
            {risk.toUpperCase()}
          </Tag>
        </div>
        <div className="risk-card__item">
          <span className="risk-card__label">BLAST RADIUS</span>
          <span className="risk-card__value">{blastRadius}</span>
        </div>
        <div className="risk-card__item risk-card__item--full">
          <span className="risk-card__label">RECOMMENDATION</span>
          <span className="risk-card__value">{recommendation}</span>
        </div>
      </div>
    </div>
  )
}

export default RiskAssessmentCard
