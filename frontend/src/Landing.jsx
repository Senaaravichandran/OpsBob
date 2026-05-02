// OpsBob Landing Page - Cinematic full-screen entry point with glowing logo and pulsing status indicator
import { useState } from 'react'
import './Landing.css'

function Landing({ onEnter }) {
  const [fadeOut, setFadeOut] = useState(false)

  const handleEnter = () => {
    setFadeOut(true)
    setTimeout(() => {
      onEnter()
    }, 600)
  }

  return (
    <div className={`landing-container ${fadeOut ? 'fade-out' : ''}`}>
      <div className="landing-content">
        <img 
          src="/logo.png" 
          alt="OpsBob Logo" 
          className="landing-logo"
        />
        <h1 className="landing-title">OPSBOB</h1>
        <p className="landing-subtitle">AUTONOMOUS PRODUCTION INTELLIGENCE</p>
        
        <div className="status-indicator">
          <span className="pulse-dot"></span>
          <span className="status-text">SYSTEM ONLINE</span>
        </div>

        <button className="enter-button" onClick={handleEnter}>
          ENTER COMMAND CENTER
        </button>
      </div>
    </div>
  )
}

export default Landing

// Made with Bob
